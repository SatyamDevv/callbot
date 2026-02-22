# 📞 AI Voice Caller Agent (Raspberry Pi + SIM7600)

A powerful, open-source Voice AI Agent capable of making and receiving phone calls, conversing naturally in Hinglish (Hindi + English), and booking meetings automatically. Powered by **Google Gemini Live API** and running on a **Raspberry Pi 4B** with a **SIM7600G-H 4G GSM Module**.

## 📺 Live Demo

Coming soon! I will be posting a full video demonstration of this agent in action on LinkedIn.
Stay tuned here: **[Watch the Demo on LinkedIn](https://www.linkedin.com/in/satyamdevv)** _(Link will be updated once the post is live!)_

## 💡 Project Motivation

This project was born out of a simple need: **Helping small business owners save time.**
Business owners often miss critical calls while working. This AI system acts as a 24/7 assistant that can:

- **Automated Reception**: Take calls and book appointments when you are unavailable.
- **Lead Capture**: Automatically gather potential client details so no inquiry is missed.
- **Customer Support**: Answer frequent questions (FAQ) about your services or business hours.
- **After-Hours Assistant**: Handle inquiries late at night so you can rest.

_This system ensures that even if you can't pick up the phone, your business is still talking to your clients._

## 🌟 Features

- **Real-time Voice Conversation**: Uses Google's Gemini Live (Multimodal Live API) for low-latency, natural voice interactions.
- **Hinglish Support**: Specifically prompted to speak in a natural, conversational Indian context.
- **Auto-Meeting Booking**: Detects user intent during calls and automatically saves meeting details.
- **Interruption Handling (Barge-in)**: The AI is smart—if you start speaking while it's talking, it immediately stops and listens to you, making the conversation feel human-like.

## 🚀 Future Extensions & Possibilities

This project is designed to be highly extensible. Here are some ways you can scale and upgrade this system:

### 1. The "Caller Farm" (Multi-Line AI Call Center)

While a single Raspberry Pi + SIM7600 handles one concurrent call, you can scale this into a multi-agent call center:

- **Hardware Scaling**: Use a **GoIP GSM Gateway** (4, 8, 16, or 32 SIM slots) connected to a local SIP server (Asterisk/FreePBX) on the Pi.
- **Cloud Scaling**: Replace the SIM module with a VoIP provider like **Twilio** or **Plivo** to handle dozens of concurrent Gemini Live streams in the cloud.

### 2. Agentic AI Integration (OpenClaw / NanoClaw)

You can upgrade the AI from a simple voice bot to a fully autonomous AI employee using lightweight agent frameworks like **NanoClaw** or **PicoClaw**:

- **Live Tool Calling**: Give the AI Python functions to execute during the call. For example, checking a live Google Calendar, querying a database, or triggering the SIM7600 to send an SMS (`AT+CMGS`) _while_ talking to the user.
- **Long-Term Memory**: The agent can remember past callers. If a customer calls back 3 hours later, the AI can say, _"Hello Rakesh, did you get the pricing email I sent earlier?"_
- **Call Transfers**: Program the AI to send DTMF tones or AT commands to transfer complex calls to your personal number.

## 🏗️ System Workflow

![System Workflow Diagram](images/workflow.png)

## 🛠️ Hardware Requirements

To build this project, you will need the following components:

1.  **Raspberry Pi 4B Kit**:
    - Recommended: 4GB or 8GB RAM version.
    - **CRITICAL**: Use the **Original Raspberry Pi Power Supply**. Using a generic phone charger will cause voltage drops and unstable behavior with the GSM module (which has high power spikes).
2.  **SIM7600G-H 4G GSM Module**:
    - **CRITICAL**: You MUST use this specific module (because it support audio stream via USB).
    - **Reason**: It is one of the few modules that supports **direct PCM audio streaming** from the Raspberry Pi via USB (no external sound cards or complex wiring required).
    - Supports 4G/3G/2G communication and GNSS positioning.
3.  **SIM Card**:
    - **Preferred**: **Airtel** (Recommended for better 3G/VoLTE fallback support).
    - **Note**: I personally experienced compatibility issues with Jio SIMs in this setup, so they are not recommended.
4.  **USB Cable**:
    - A high-quality **USB Type-C cable** to connect the GSM Module's data port to the Raspberry Pi's USB port.

## 📦 Software Setup

### 1. Initial Pi & SIMCOM Setup

1.  **Install Raspberry Pi OS**: Flash the standard Raspberry Pi OS to your SD card.
2.  **Connect Network**: Ensure your Pi is connected to WiFi or Ethernet.
3.  **Install SIMCOM Config**: You need to set up the SIM7600 module drivers/configuration ("Simcom").
    - **Reference Docs**: [Waveshare SIM7600G-H 4G HAT (B) Wiki](<https://www.waveshare.com/wiki/SIM7600G-H_4G_HAT_(B)?srsltid=AfmBOophSK7miRfRJ6Sv1oLdkLjEkaLM8t-QdN2mZuI_XMOV7KhIClGs>)
    - Follow the wiki to ensure the module is recognized and the USB audio drivers are working.

### 2. System Dependencies

Ensure your Raspberry Pi OS is up to date and you have Python 3.11+ installed.

```bash
sudo apt update && sudo apt upgrade
sudo apt install python3-pip python3-venv portaudio19-dev
```

### 3. Install Python Libraries

Create a virtual environment (optional but recommended) and install the required Python libraries:

```bash
pip install pyserial numpy google-genai --break-system-packages
```

_Note: On newer Raspberry Pi OS versions (Bookworm+), you may need the `--break-system-packages` flag if you are not using a virtual environment._

_Note: You may need to create a Google Cloud Project and enable the Gemini API._

### 4. Configuration

1.  Open the script (e.g., `main.py`).
2.  **API Key**: Replace the placeholder `GEMINI_API_KEY` with your actual Google Gemini API Key.
    - **⚡ Security Tip**: Never commit your API key to GitHub! It's best to use an environment variable or a `.env` file to keep your keys safe.
3.  **Model Selection**:
    - Currently set to `MODEL_NAME = "models/gemini-2.5-flash-native-audio-preview-12-2025"`.
    - **Future Updates**: If the code stops working, this model name might have changed. Visit [Google AI Studio](https://aistudio.google.com/), select the **Multimodal Live** feature, click **"Get Code"**, and find the string `MODEL_NAME = "..."`. Copy and paste that value into the script.
    - **Tier**: This project works perfectly fine on the **Free Version** of the Gemini API Key.

## 🚀 Usage

1.  Connect the SIM7600 module to the Raspberry Pi via USB.
2.  Power on the Pi and ensure the SIM card has network connectivity (Status LED blinking slowly).
3.  Run the agent:

```bash
python 26jan_imporvemnet.py
```

4.  **Call the number** associated with the SIM card.
5.  The AI will answer via the script:
    - _"Hello, main Satyam ki AI assistant baat kar rahi hoon..."_
6.  **Book a Meeting**:
    - Say: _"Mujhe meeting book karni hai"_ (I want to book a meeting).
    - Provide your **Name**, **Reason**, and **Phone Number**.
    - The script will detect the details and save them to `bookings.json`.

## 📂 Project Structure

```
.
├── 26jan_imporvemnet.py    # Core logic (AT commands, Audio handling, Gemini API)
├── bookings.json       # Auto-generated file storing meeting requests
└── README.md           # This documentation
```

## ⚠️ Troubleshooting

- **ConnectionClosedError**: If you see this from the Gemini API, ensure you are using the correct `response_modalities`. The Preview model currently works best with `["AUDIO"]`.
- **Low Voltage Warning**: If your Pi throttles or the GSM module resets, **CHECK YOUR POWER SUPPLY**. The SIM7600 draws over 2A during calls.
- **Audio Noise**: Ensure the USB cable is high quality and not too long.

## 📊 Data Format (`bookings.json`)

The system automatically captures details in a structured JSON file:

```json
[
  {
    "timestamp": "2026-01-26T20:46:01",
    "name": "Rakesh Sharma",
    "reason": "Website Project Inquiry",
    "phone": "9876543210",
    "raw_text": "|| BOOK_MEETING || Name: Rakesh Sharma, Reason: Website Project, Phone: 9876543210"
  }
]
```

## 💰 Estimated Budget

Building this kit costs approximately:

- **INR**: ₹12,000 - ₹14,000
- **USD**: $145 - $170 (approx.)

_Note: Prices may vary based on your location and vendor choice._

## 🤝 Contributing

Open to contributions! Feel free to submit Pull Requests for better prompt engineering, more robust error handling, or support for other GSM modules.

## 📬 Contact

Feel free to reach out for collaborations or queries:

- **Email**: [satyamtiwari2001@gmail.com](mailto:satyamtiwari2001@gmail.com)
- **LinkedIn**: [SatyamDevv](https://www.linkedin.com/in/satyamdevv)
- **X (Twitter)**: [@SatyamDevv](https://x.com/SatyamDevv)

## 📄 License & Disclaimer

**Disclaimer**: This project is for **educational purposes only**. The creators do not promote any unethical behavior and take no responsibility for how this tool is used. Please comply with your local telecommunication laws regarding automated calling and recordings.

Open Source. Feel free to use and modify.
