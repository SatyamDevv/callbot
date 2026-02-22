#!/usr/bin/env python3

import asyncio
import time
import re
import serial
import numpy as np
import json
import os
from datetime import datetime
from google import genai
from google.genai import types

# --- TOOL DEFINITION ---
def book_meeting(name: str, reason: str, phone: str = "Unknown", raw_text: str = ""):
    """Books a meeting by saving details to a JSON file."""
    print(f"\n[Tool] Attempting to book meeting for {name}...", flush=True)
    filename = "bookings.json"
    filepath = os.path.abspath(filename)
    
    entry = {
        "timestamp": datetime.now().isoformat(),
        "name": name,
        "reason": reason,
        "phone": phone,
        "raw_text": raw_text
    }
    
    data = []
    try:
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
            except Exception as e:
                print(f"[Tool] Warning: Could not read existing bookings: {e}", flush=True)
                
        data.append(entry)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
            
        print(f"\n[Tool] Meeting booked for {name}: {reason}", flush=True)
        print(f"[Tool] Saved to: {filepath}", flush=True)
        return {"status": "success", "message": f"Meeting booked successfully for {name}."}
        
    except Exception as e:
        print(f"\n[Tool] ERROR: Failed to save booking to {filepath}: {e}", flush=True)
        return {"status": "error", "message": f"Failed to save booking: {str(e)}"}

tool_book_meeting = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="book_meeting",
            description="Book a meeting or call with Satyam. Requires name and reason.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "name": types.Schema(type="STRING", description="Name of the person wanting to meet"),
                    "reason": types.Schema(type="STRING", description="Reason for the meeting"),
                    "phone": types.Schema(type="STRING", description="Phone number if provided")
                },
                required=["name", "reason"]
            )
        )
    ]
)

# --- CONFIG ---
AT_PORT = "/dev/ttyUSB2"
AUDIO_PORT = "/dev/ttyUSB4"
BAUD = 460800
PHONE_NUMBER = "7777777777"

# ==============================================================================
# CRITICAL: STEP 1 - VERIFY THIS VALUE
# ==============================================================================
GEMINI_API_KEY = ""

# Initialize the client
client = genai.Client(api_key=GEMINI_API_KEY)

# ==============================================================================
# CRITICAL: STEP 2 - VERIFY THIS MODEL NAME
# ==============================================================================
MODEL_NAME = "models/gemini-2.5-flash-native-audio-preview-12-2025"

CONFIG = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Zephyr") # This is a female voice
        )
    ),
    tools=None # Disabled due to policy violation in preview model
)

# --- Audio Conversion Utilities (using only NumPy) ---

def upsample_8k_to_16k(pcm8: bytes) -> bytes:
    """
    Upsamples 8kHz PCM audio to 16kHz using NumPy's linear interpolation.
    """
    samples_8k = np.frombuffer(pcm8, dtype=np.int16)
    if len(samples_8k) == 0:
        return b""
    
    original_indices = np.arange(len(samples_8k))
    target_indices = np.linspace(0, len(samples_8k) - 1, num=len(samples_8k) * 2)
    
    samples_16k = np.interp(target_indices, original_indices, samples_8k)
    
    return samples_16k.astype(np.int16).tobytes()

def downsample_24k_to_8k(pcm24: bytes) -> bytes:
    """
    Downsamples 24kHz PCM audio to 8kHz by averaging every 3 samples.
    """
    samples_24k = np.frombuffer(pcm24, dtype=np.int16)
    
    cutoff = len(samples_24k) - (len(samples_24k) % 3)
    if cutoff == 0:
        return b""
        
    samples_8k = samples_24k[:cutoff].reshape(-1, 3).mean(axis=1)
    
    return samples_8k.astype(np.int16).tobytes()


# --- AT Utilities ---
def at_command(ser, cmd, pause=0.5, quiet=False):
    if not ser or not ser.is_open: return ""
    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode())
    time.sleep(pause)
    resp = ser.read_all().decode(errors="ignore")
    if not quiet:
        print(f"AT -> {cmd}\n<- {resp.strip()}")
    return resp

async def wait_for_call_active(ser):
    print("Waiting for call to connect...")
    # Increase range since we are polling faster
    for _ in range(300): 
        # Reduced pause for faster command execution
        resp = at_command(ser, "AT+CLCC", 0.1)
        if re.search(r"\+CLCC:.*,0,", resp):
            print("Call is now active.")
            return True
        await asyncio.sleep(0.1) # Check every 100ms
    return False

async def is_call_active(ser):
    try:
        if not ser or not ser.is_open: return False
        resp = at_command(ser, "AT+CLCC", 0.1, quiet=True)
        return re.search(r"\+CLCC:.*,0,", resp) is not None
    except serial.SerialException:
        return False

# --- Main Voice Agent ---
async def main():
    print("Starting Gemini Live Voice Agent...")
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        print("\nFATAL ERROR: You must replace 'YOUR_GEMINI_API_KEY' in the script with your actual key.\n")
        return
        
    s_at, s_audio = None, None
    try:
        s_at = serial.Serial(AT_PORT, 115200, timeout=1)
        s_audio = serial.Serial(AUDIO_PORT, BAUD, timeout=0.05)
    except serial.SerialException as e:
        print(f"Error opening serial ports: {e}")
        return

    at_command(s_at, f"ATD{PHONE_NUMBER};", 2)
    at_command(s_at, "AT+CPCMREG=1", 0.5)

    if not await wait_for_call_active(s_at):
        print("Failed to detect active call. Exiting.")
        at_command(s_at, "AT+CHUP", 0.5)
        return

    print("\n>>> Connection established. Please begin speaking. <<<\n")

    caller_q = asyncio.Queue()
    gemini_q = asyncio.Queue()
    stop = asyncio.Event()
    gemini_is_speaking = asyncio.Event()
    interrupted = asyncio.Event()

    async def read_caller():
        read_buffer = bytearray()
        CHUNK_SIZE = 320
        while not stop.is_set():
            try:
                data = await asyncio.to_thread(s_audio.read, 1024)
                if data:
                    read_buffer.extend(data)
                    while len(read_buffer) >= CHUNK_SIZE:
                        chunk_to_send = read_buffer[:CHUNK_SIZE]
                        del read_buffer[:CHUNK_SIZE]
                        await caller_q.put(bytes(chunk_to_send))
                        print(".", end="", flush=True)
                else:
                    await asyncio.sleep(0.01)
            except Exception as e:
                print(f"\nError in read_caller: {e}\n"); stop.set()

    async def write_modem():
        while not stop.is_set():
            try:
                # ---- START: THE FIX IS HERE ----
                # Increased timeout to 1.5 seconds to handle natural pauses in AI speech
                chunk = await asyncio.wait_for(gemini_q.get(), timeout=1.5)
                # ---- END: THE FIX IS HERE ----
                
                if not gemini_is_speaking.is_set():
                    print("\n[Gemini Speaking]", flush=True)
                    gemini_is_speaking.set()
                await asyncio.to_thread(s_audio.write, chunk)
            except asyncio.TimeoutError:
                if gemini_is_speaking.is_set():
                    print("[Gemini Silent]", flush=True)
                    gemini_is_speaking.clear()
            except Exception as e:
                print(f"\nError in write_modem: {e}\n"); stop.set()

    async def monitor_call():
        while not stop.is_set():
            if not await is_call_active(s_at):
                print("\nCall ended by remote party.")
                stop.set(); break
            await asyncio.sleep(2)

    async with client.aio.live.connect(model=MODEL_NAME, config=CONFIG) as session:
        
        async def send_to_gemini():
            async def reset_interrupted():
                await asyncio.sleep(2.0)
                if interrupted.is_set():
                    interrupted.clear()
            
            initial_prompt_hindi = """
            Aap Satyam Tiwari ki ek female AI assistant hain. 
            
            Important Instructions:
            - Ye ek voice call hai, isliye hamesha chote, clear aur conversational natural Hinglish (Hindi + English mix) mein jawaab dena.
            - Bullet points, lists, ya lambe sentences bilkul use mat karna. Aise baat karo jaise ek normal insaan phone pe karta hai.
            - Apni sari baaton mein hamesha feminine grammar (female gender) use karna. Jaise 'main kar sakti hoon', 'mujhe pata hai', 'aa rahi hoon'. 'Main kar sakta hoon' kabhi mat bolna.

            Satyam Tiwari ke baare mein info:
            Satyam abhi Minerva Capital Research Solutions mein Team Lead hain aur IIIT Ranchi aur IIT Patna se MCA kar rahe hain.
            Woh ek Full Stack Developer hain. Unhe frontend mein React.js, Next.js, Tailwind CSS aur Shadcn aata hai.
            Backend mein woh Node.js, Express.js aur Flask mein expert hain. Database mein unhe MongoDB, SQL aur Firebase ka idea hai.
            Woh Python, Java, JavaScript aur TypeScript programming languages jaante hain.

            Tasks:
            - Agar koi Satyam se milna chahta hai ya call book karna chahta hai (jaise bole 'mujhe meeting book krni hai'), toh uska Naam (Name), Kaaran (Reason) aur Mobile Number poochna.
            - Jab wo teeno details de de:
              1. Pehle user ko AUDIO mein normal confirm karo: "Theek hai, maine details note kar li hain."
              2. FIR TURANT apne THOUGHT/TEXT mein ye specific command likho (System ke liye):
                 || BOOK_MEETING || Name: [Asli Naam], Reason: [Asli Reason], Phone: [Asli Phone]
            
            - Ye "|| BOOK_MEETING ||" wala command TEXT/THOUGHT mein aana zaroori hai. Isse hi meeting save hogi.
            - Baaki conversation normal rakhein.

            Call start hone par aapko aise introduce karna hai: "Hello, main Satyam ki AI assistant baat kar rahi hoon. Batayein, main aapki kaise help kar sakti hoon?"
            """
            
            try:
                # Wait for 0.5 seconds to ensure audio channel is stable
                print("Call active. Waiting 0.5s before greeting...")
                await asyncio.sleep(0.5)
                
                print("Sending initial prompt to Gemini...")
                await session.send_realtime_input(text=initial_prompt_hindi)
                print("Initial prompt sent successfully.")
            except Exception as e:
                print(f"\nError sending initial prompt: {e}\n")
                stop.set()
                return
            
            buffer = bytearray()
            while not stop.is_set():
                try:
                    pcm8 = await asyncio.wait_for(caller_q.get(), timeout=0.1)
                    
                    # Interruption Handling / Barge-In
                    pcm16 = upsample_8k_to_16k(pcm8)
                    
                    # Check for voice activity (simple RMS threshold)
                    # We only care about interrupting if Gemini is currently speaking
                    if gemini_is_speaking.is_set():
                        samples = np.frombuffer(pcm16, dtype=np.int16)
                        if len(samples) > 0:
                            sq = samples.astype(np.float32) ** 2
                            mean_sq = np.mean(sq)
                            rms = np.sqrt(mean_sq)
                            
                            if rms > 2500: 
                                print(" [INTERRUPT] ", end="", flush=True) 
                                interrupted.set() # Flag that we are in interrupted state
                                asyncio.create_task(reset_interrupted()) # Failsafe reset
                                while not gemini_q.empty():
                                    try: gemini_q.get_nowait()
                                    except asyncio.QueueEmpty: break
                                gemini_is_speaking.clear()
                                # Optionally send a signal to Gemini to stop context (optional)
                                # await session.send_realtime_input(text="[INTERRUPTED]") 

                    buffer.extend(pcm16)
                    if len(buffer) >= 3200:
                        if interrupted.is_set(): interrupted.clear() # Reset flag when user speaks meaningful amount
                        await session.send_realtime_input(media=types.Blob(data=bytes(buffer), mime_type="audio/pcm"))
                        buffer.clear()
                        print("S", end="", flush=True)
                except asyncio.TimeoutError:
                    if buffer:
                        if interrupted.is_set(): interrupted.clear() # Reset flag here too
                        await session.send_realtime_input(media=types.Blob(data=bytes(buffer), mime_type="audio/pcm"))
                        buffer.clear()
                        print("s", end="", flush=True)
                except Exception as e:
                    print(f"\nError in send_to_gemini: {e}\n"); stop.set()

        async def receive_from_gemini():
            while not stop.is_set():
                try:
                    async for resp in session.receive():
                        if stop.is_set(): break
                        
                        # Inspect non-audio parts
                        if resp.server_content and resp.server_content.model_turn:
                            for part in resp.server_content.model_turn.parts:
                                if part.text:
                                    text = part.text
                                    print(f"\n[Gemini Text]: {text}")
                                    
                                    # --- STRATEGY 1: Explicit Trigger Match ---
                                    # We iterate through ALL matches because the model might mention the command in its thought
                                    trigger_iter = re.finditer(r"\|\|\s*BOOK[_\s]MEETING\s*\|\|", text, re.IGNORECASE)
                                    
                                    found_valid_action = False
                                    
                                    for trigger_match in trigger_iter:
                                        try:
                                            start_index = trigger_match.end()
                                            detail_part = text[start_index:].strip()
                                            
                                            # Regex to extract Name, Reason, Phone with robust lookaheads
                                            name = "Unknown"; reason = "Unknown"; phone = "Unknown"
                                            
                                            name_match = re.search(r"Name:\s*(.*?)(?:,?\s*Reason:|\||$)", detail_part, re.IGNORECASE)
                                            if name_match: name = name_match.group(1).strip()
                                            
                                            reason_match = re.search(r"Reason:\s*(.*?)(?:,?\s*Phone:|\||$)", detail_part, re.IGNORECASE)
                                            if reason_match: reason = reason_match.group(1).strip()
                                            
                                            phone_match = re.search(r"Phone:\s*(.*?)(?:,|$)", detail_part, re.IGNORECASE)
                                            if phone_match: phone = phone_match.group(1).strip()
                                            
                                            if name != "Unknown" and len(name) > 0:
                                                print(f"\n[Action Detected (Trigger)] Booking meeting for {name} ({reason})...", flush=True)
                                                book_meeting(name, reason, phone, raw_text=detail_part)
                                                found_valid_action = True
                                                break 
                                        except Exception as e:
                                            print(f"\n[Trigger Error] {e}", flush=True)
                                    
                                    # --- STRATEGY 2: Fallback Pattern Match (No Trigger) ---
                                    if not found_valid_action:
                                        # Look for "Name: ... Phone: ..." pattern anywhere in text
                                        try:
                                            if "Name:" in text and "Phone:" in text:
                                                name = "Unknown"; reason = "Unknown"; phone = "Unknown"
                                                
                                                name_match = re.search(r"Name:\s*(.*?)(?:,?\s*Reason:|\||\n|$)", text, re.IGNORECASE)
                                                if name_match: name = name_match.group(1).strip()
                                                
                                                reason_match = re.search(r"Reason:\s*(.*?)(?:,?\s*Phone:|\||\n|$)", text, re.IGNORECASE)
                                                if reason_match: reason = reason_match.group(1).strip()
                                                
                                                phone_match = re.search(r"Phone:\s*(.*?)(?:,|$|\n)", text, re.IGNORECASE)
                                                if phone_match: phone = phone_match.group(1).strip()
                                                
                                                if name != "Unknown" and len(name) < 50: # Sanity check length
                                                     print(f"\n[Action Detected (Fallback)] Booking meeting for {name}...", flush=True)
                                                     book_meeting(name, reason, phone, raw_text=text)
                                                     found_valid_action = True
                                        except Exception: pass

                                    # --- STRATEGY 3: Last Resort (Phone Number Detection) ---
                                    if not found_valid_action:
                                        # If we see a 10 digit number and keywords like "meeting" or "book"
                                        try:
                                            phone_scan = re.search(r"\b\d{10}\b", text)
                                            if phone_scan:
                                                extracted_phone = phone_scan.group(0)
                                                print(f"\n[Action Detected (Phone Scan)] Found phone number {extracted_phone}, saving as potential booking...", flush=True)
                                                # Save what we have
                                                book_meeting("Extracted from Text", "See Raw Text", extracted_phone, raw_text=text)
                                                found_valid_action = True
                                        except Exception: pass


                        if resp.data:
                            if interrupted.is_set():
                                continue # Drop audio packets if interrupted
                            pcm8 = downsample_24k_to_8k(resp.data)
                            await gemini_q.put(pcm8)
                            print("R", end="", flush=True)
                except Exception as e:
                    if not stop.is_set():
                        print(f"\nError in receive_from_gemini stream: {e}\n")
                    await asyncio.sleep(0.1)

        tasks = [
            asyncio.create_task(read_caller()),
            asyncio.create_task(write_modem()),
            asyncio.create_task(send_to_gemini()),
            asyncio.create_task(receive_from_gemini()),
            asyncio.create_task(monitor_call())
        ]

        try:
            await stop.wait()
        except KeyboardInterrupt:
            print("\nInterrupted by user.")
        finally:
            if not stop.is_set(): stop.set()
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    print("Conversation ended. Hanging up...")
    at_command(s_at, "AT+CHUP", 0.5)
    if s_at: s_at.close()
    if s_audio: s_audio.close()
    print("Agent terminated successfully.")

if __name__ == "__main__":
    asyncio.run(main())
