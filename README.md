# Social Interaction Cloud (SIC)

> **Build social robot applications without reinventing the wheel.**

SIC is a Python framework that lets you connect robots, AI services, and sensors together — so you can focus on designing interactions, not wiring up infrastructure.

---

## What Does SIC Do?

Imagine you want a robot to:

1. 📷 **See** — use its camera to detect faces  
2. 🎤 **Listen** — transcribe what a person says  
3. 🧠 **Think** — generate a response with a large language model
4. 🗣️ **Speak** — say the answer out loud  

Normally, you'd need to integrate each SDK, manage network communication between devices, and synchronize everything yourself. **SIC handles all of that.** You write a short Python script; SIC takes care of the rest.

```python
from sic_framework.devices import Nao
from sic_framework.services import FaceDetection

# Connect to the robot
nao = Nao("192.168.1.100")
camera = nao.camera()

# Start an AI service and receive results
face_detector = FaceDetection()
camera.register_callback(on_new_image)
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| 🤖 **Multi-Robot Support** | NAO, Pepper, AlphaMini, Franka Emika, Reachy Mini, and Desktop |
| 🧠 **Built-in AI Services** | Speech recognition, text-to-speech, GPT, face detection, object detection, and more |
| 🔌 **Modular Architecture** | Plug-and-play components — mix and match sensors, services, and actuators |
| 🌐 **Distributed by Design** | Components can run on different machines and communicate over the network |
| 👥 **Multi-User Access** | Built-in reservation system so multiple researchers can share the same robot |
| 🐳 **Docker Support** | Run AI services in containers with a single command |
| 🔗 **MCP Integration** | Let LLM agents (ChatGPT, Claude, etc.) control the robot via the Model Context Protocol |

---

## How It Works

SIC uses [Redis](https://redis.io/) as a message bus. Every component — whether it's a camera on a robot, a face detection model on a GPU server, or your Python script on a laptop — communicates through Redis channels.

```
 Your Computer               Redis Server              Robot (NAO / Pepper)
┌────────────────┐          ┌────────────┐           ┌────────────────────┐
│  Python script │ ◄─msg──► │   Redis    │ ◄──msg──► │  Camera sensor     │
│  (Connectors)  │          │  (Pub/Sub) │           │  Microphone        │
└────────────────┘          └────────────┘           │  Speakers / Motors │
       ▲                         ▲                   └────────────────────┘
       │                         │
       ▼                         ▼
┌────────────────┐          ┌────────────┐
│  AI Services   │ ◄─msg──► │   Redis    │
│  (GPT, STT,    │          │            │
│   Face Det.)   │          └────────────┘
└────────────────┘
```

### Building Blocks

SIC applications are built by connecting three types of **Components**:

| Component | Role | Examples |
|-----------|------|----------|
| **Sensor** | Collects data from the environment | Camera, microphone |
| **Service** | Transforms data using AI / logic | Face detection, speech-to-text, GPT |
| **Actuator** | Performs physical actions | Speaking, moving joints, displaying on a tablet |

These components are managed behind the scenes by:

- **ComponentManager** — starts and stops components on each device  
- **Connector** — your remote control to interact with any component from your script  
- **SICApplication** — manages the lifecycle of your entire program (connections, shutdown, logging)

---

## Supported Platforms

### Robots

| Platform | Connection | Notes |
|----------|-----------|-------|
| [**NAO**](https://www.aldebaran.com/en/nao) | SSH + Redis | Python 2.7 on the robot, Python 3.10+ on your machine |
| [**Pepper**](https://www.aldebaran.com/en/pepper) | SSH + Redis | Same as NAO; includes tablet, bumpers, depth camera |
| [**AlphaMini**](https://www.ubtrobot.com/products/alphamini) | WebSocket + Redis | Requires `alphamini` SDK |
| [**Franka Emika**](https://franka.de/) | panda-python + Redis | Research robot arm |
| [**Reachy Mini**](https://www.pollen-robotics.com/reachy-mini/) | reachy-mini SDK | Expressive tabletop robot |
| **Desktop** | Local hardware | Use your laptop's camera, mic, and speakers |

### AI Services

| Service | Technology | Install Extra |
|---------|-----------|---------------|
| Speech-to-Text (Google) | Google Cloud Speech | `pip install .[google-stt]` |
| Speech-to-Text (Whisper) | OpenAI Whisper API | `pip install .[whisper-speech-to-text]` |
| Speech-to-Text (Local Whisper) | faster-whisper / mlx-whisper | `pip install .[local-whisper-stt]` |
| Text-to-Speech (Google) | Google Cloud TTS | `pip install .[google-tts]` |
| Text-to-Speech (ElevenLabs) | ElevenLabs API | `pip install .[elevenlabs-tts]` |
| LLM (OpenAI GPT) | OpenAI API | `pip install .[openai-gpt]` |
| LLM (Nebula) | OpenAI-compatible API | `pip install .[nebula]` |
| Face Detection | DNN / Haar Cascade | *(included by default)* |
| Object Detection | Ultralytics YOLO | `pip install .[object-detection]` |
| Voice Activity Detection | PyTorch audio | `pip install .[voice-detection]` |
| Dialogflow | Google Cloud Dialogflow | `pip install .[dialogflow]` |
| Dialogflow CX | Google Cloud Dialogflow CX | `pip install .[dialogflow-cx]` |
| Speaker Diarization | NVIDIA NeMo SortFormer | `pip install .[sortformer]` |
| MCP (Robot-as-Tool for LLMs) | LangChain + FastMCP | `pip install .[mcp]` |

---

## Installation

> **Requirements:** Python 3.10–3.12, [Redis](https://redis.io/docs/latest/get-started/)

### 1. Install SIC

```bash
pip install social-interaction-cloud
```

Or install from source with optional extras:

```bash
git clone https://github.com/Social-AI-VU/social-interaction-cloud.git
cd social-interaction-cloud
pip install -e .                    # core only
pip install -e ".[openai-gpt]"     # with GPT support
pip install -e ".[dev]"            # with development tools
```

### 2. Install and Start Redis

**Ubuntu / Debian:**
```bash
sudo apt install redis
redis-server conf/redis/redis.conf
```

**macOS:**
```bash
brew install redis
redis-server conf/redis/redis.conf
```

**Windows:**
```bash
# Download Redis from https://github.com/microsoftarchive/redis/releases
# or use Docker:
docker run -d -p 6379:6379 --name redis redis:latest
```

### 3. Configure Environment

Create a `.env` file (or copy from `sic_applications/conf/.example_env`):

```env
DB_IP=localhost
DB_PASS=changemeplease
OPENAI_API_KEY=your-key-here  # optional, for GPT/Whisper services
```

### 4. Run Your First Application

Clone the demo applications:

```bash
git clone https://github.com/Social-AI-VU/sic_applications.git
cd sic_applications/demos/desktop
python demo_desktop_camera.py
```

This opens your webcam feed through SIC's component system. If it works, you're all set! 🎉

---

## Project Structure

```
social-interaction-cloud/
├── setup.py                        # Package configuration & extras
├── conf/redis/                     # Redis server configuration
├── docs/                           # Sphinx documentation source
└── sic_framework/                  # Main framework package
    ├── core/                       # ← Framework internals
    │   ├── component_python2.py    #   Base class for all components
    │   ├── component_manager_python2.py  #   Starts/stops components on hosts
    │   ├── connector.py            #   User API to interact with components
    │   ├── message_python2.py      #   Message types & serialization
    │   ├── sic_redis.py            #   Redis pub/sub wrapper
    │   ├── sic_application.py      #   Application lifecycle (singleton)
    │   ├── service_python2.py      #   Service base (with input alignment)
    │   ├── sensor_python2.py       #   Sensor base (continuous data)
    │   ├── actuator_python2.py     #   Actuator base (request-reply)
    │   └── sic_compose.py          #   Docker Compose lifecycle helpers
    ├── devices/                    # ← Robot platform drivers
    │   ├── nao.py, pepper.py       #   SoftBank Robotics (NAOqi)
    │   ├── alphamini.py            #   UBTech AlphaMini
    │   ├── franka.py               #   Franka Emika robot arm
    │   ├── reachy_mini.py          #   Pollen Robotics Reachy Mini
    │   ├── desktop.py              #   Local machine (camera/mic/speakers)
    │   └── common_*/               #   Platform-specific sensors & actuators
    ├── services/                   # ← AI & processing services
    │   ├── llm/                    #   GPT, Nebula (LLM wrappers)
    │   ├── google_stt/             #   Google Speech-to-Text
    │   ├── google_tts/             #   Google Text-to-Speech
    │   ├── elevenlabs_tts/         #   ElevenLabs Text-to-Speech
    │   ├── openai_whisper_stt/     #   Whisper Speech-to-Text
    │   ├── local_whisper_stt/      #   Local Whisper (faster-whisper/mlx)
    │   ├── face_detection/         #   Face detection (DNN/Haar)
    │   ├── object_detection/       #   YOLO object detection
    │   ├── voice_detection/        #   Voice activity detection
    │   ├── streaming_sortformer/   #   Speaker diarization
    │   ├── webserver/              #   Flask web interface
    │   └── templates/              #   Templates for creating new components
    ├── mcp/                        # ← Model Context Protocol
    │   ├── mcp_server.py           #   MCP server base class
    │   ├── mcp_client.py           #   LangChain MCP client
    │   └── nao/                    #   NAO MCP implementation
    └── docker/                     # ← Docker images for services
```

---

## Architecture Deep Dive

### Component Lifecycle

```
User Script                    ComponentManager (on device)         Component
     │                                │                                │
     │  SICStartComponentRequest      │                                │
     │ ──────────────────────────►    │                                │
     │                                │  create + start thread         │
     │                                │ ─────────────────────────────► │
     │                                │                   ready_event  │
     │  SICComponentStartedMessage    │  ◄──────────────────────────── │
     │ ◄──────────────────────────    │                                │
     │                                │                                │
     │         (messages / requests flow via Redis pub/sub)            │
     │ ◄─────────────────────────────────────────────────────────────► │
     │                                │                                │
     │  SICStopComponentRequest       │                                │
     │ ──────────────────────────►    │  stop + cleanup                │
     │                                │ ─────────────────────────────► │
```

### Message Types

All data flows through `SICMessage` objects, serialized with Python's Pickle (protocol 2 for Python 2/3 cross-compatibility):

- **SICMessage** — one-way broadcast (async)
- **SICRequest → SICMessage** — request-reply (sync, with timeout)
- **CompressedImageMessage** — JPEG-compressed image (via TurboJPEG)
- **AudioMessage** — PCM 16-bit audio data
- **TextMessage** — plain text
- **BoundingBoxesMessage** — detection results with coordinates

### Multi-Input Synchronization

`SICService` automatically aligns inputs from multiple sources by timestamp. For example, a sentiment analysis service that needs both audio and text will wait until it has time-aligned data from both before calling `execute()`.

---

## Creating Custom Components

SIC includes templates to help you create your own components:

```
sic_framework/services/templates/
├── template_sensor.py        # Continuous data producer
├── template_actuator.py      # Request-reply action performer
├── template_service.py       # Data transformer
└── template_component.py     # Generic component
```

---

## Documentation

📖 **Full documentation:** [social-ai-vu.github.io/social-interaction-cloud](https://social-ai-vu.github.io/social-interaction-cloud/)

📦 **Demo applications:** [github.com/Social-AI-VU/sic_applications](https://github.com/Social-AI-VU/sic_applications)

📹 **Video tutorial:** [Installation & Setup (YouTube)](https://www.youtube.com/watch?v=nwWe2pSOuY4)

---

## CLI Commands

SIC provides command-line shortcuts to start services:

```bash
run-face-detection          # Start face detection service
run-gpt                     # Start OpenAI GPT service
run-whisper                 # Start Whisper STT service
run-google-tts              # Start Google TTS service
run-google-stt              # Start Google STT service
run-elevenlabs-tts          # Start ElevenLabs TTS service
run-object-detection        # Start YOLO object detection service
run-voice-detection         # Start voice activity detection
run-webserver               # Start Flask web interface
run-dialogflow              # Start Dialogflow service
run-dialogflow-cx           # Start Dialogflow CX service
run-nebula                  # Start Nebula LLM service
run-redis                   # Start Redis datastore service
run-sortformer              # Start SortFormer diarization
run-local-whisper           # Start local Whisper STT
run-nao-mcp                 # Start NAO MCP server
```

---

## Citation

If you use SIC in your research, please cite:

```bibtex
@software{sic,
  title   = {Social Interaction Cloud},
  author  = {Ligthart, Mike E.U. and Brown, Landon and Schwarzenbach, Lilly and Hindriks, Koen V.},
  url     = {https://github.com/Social-AI-VU/social-interaction-cloud},
  license = {MIT}
}
```

---

## Contributing

We welcome contributions! Please see the [contribution guidelines](https://social-ai-vu.github.io/social-interaction-cloud/contributions.html) in the documentation.

**Development setup:**

```bash
pip install -e ".[dev]"
pre-commit install
```

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Developed at <a href="https://vu.nl">Vrije Universiteit Amsterdam</a> · <a href="https://socialrobotics.atlassian.net/wiki/spaces/CBSR">Social AI Group</a>
</p>
