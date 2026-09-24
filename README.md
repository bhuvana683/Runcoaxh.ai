# FitCoach AI 🏋️

An intelligent, multi-modal AI fitness and nutrition coach built on the **Google Agent Development Kit (ADK)** and deployed to **Google Cloud Agent Runtime**. FitCoach AI provides personalized workout plans, 1-Rep Max (1RM) training calculations, Firestore workout logging, nutrition macro lookup, gym discovery, A2UI rich interface cards, image milestone badges, and Omni model exercise video demonstrations.

![FitCoach AI Demo](./demo.gif)

---

## 🌟 Key Features & Architecture

FitCoach AI leverages a modular agent architecture built with Google Cloud native tools and services:

- **Durable Cross-Session Memory**: Integrates **Vertex AI Memory Bank** (`VertexAiMemoryBankService`) via `PreloadMemoryTool` and callback hooks to automatically extract and remember user dietary restrictions, allergies, and fitness goals across sessions.
- **Firestore Workout History Persistence**: Real-time workout logging (`log_workout`) and retrieval (`get_workout_history`) backed by **Google Cloud Firestore**.
- **Public Media Cloud Storage**: Stores generated fitness milestone badges and exercise videos directly in a public **Google Cloud Storage (GCS)** bucket (`fitcoach-ai-media-...`).
- **Multimodal Badge & Graphic Generation**: Generates custom achievement badges using **Vertex AI Imagen 3** (`generate_workout_badge`), saving artifacts to the ADK Playground and uploading to GCS.
- **Google Omni Model Video Demonstrations**: Generates short exercise videos (`generate_exercise_video`) powered by `gemini-omni-flash-preview` in the `global` region.
- **Generative A2UI Interfaces**: Emits **A2UI (v0.8 Basic Catalog)** rich cards (`a2ui_callback`), rendering responsive UI components (Cards, Columns, Rows, Text, and Images) directly in the web interface.
- **Python Code Execution Sandbox**: Uses ADK's `BuiltInCodeExecutor` for verified mathematical calculations (e.g. 1RM percentage training bands, macro totals).
- **Custom FastAPI Proxy & Responsive Frontend**: Web UI built with Google Font `Outfit`, dark header aesthetics, active status badges, quick prompt chips, and message bubble streams connected to the agent over the A2A protocol.

---

## 🛠️ Integrated Function Tools & Services

| Service / Tool Name | Implementation Details |
| :--- | :--- |
| **Vertex AI Memory Bank** | `PreloadMemoryTool` & `generate_memories_callback` for durable fact persistence across sessions |
| **Firestore Persistence** | `log_workout`, `get_workout_history` (Collection: `workout_history`) |
| **Cloud Storage** | Public GCS Bucket (`fitcoach-ai-media-...`) for badge images & exercise videos |
| **Imagen 3 Image Gen** | `generate_workout_badge` via `genai.Client` (`gemini-omni-flash-preview` / Imagen) |
| **Omni Video Gen** | `generate_exercise_video` using `gemini-omni-flash-preview` (location: `global`) |
| **A2UI Schema Manager** | `A2uiSchemaManager` with `BasicCatalog` (Card, Column, Row, Text, Image) |
| **Code Sandbox** | `BuiltInCodeExecutor` for safe execution of Python formulas |
| **Exercise Library** | `get_exercises(category, difficulty)` |
| **1RM Calculator** | `calculate_one_rep_max(weight_lbs, reps)` using Epley formula |
| **Nutrition Lookup** | `search_food_nutrition(food_query)` |
| **Geocoding & Places** | `geocode_address(address)` & `find_nearby_places(location_query, place_type)` |
| **Time & Weather** | `get_current_time(query)` & `get_weather(query)` |

---

## 🚀 Local Setup & Running Instructions

### 1. Prerequisites
- Python 3.10+
- Google Cloud SDK (`gcloud`) authenticated with a project containing Vertex AI APIs enabled
- `uv` or `pip`

### 2. Environment Configuration
Ensure your Google Cloud credentials and project variables are set in your shell:
```bash
export GOOGLE_CLOUD_PROJECT="<your-gcp-project-id>"
export AGENT_ENGINE_RESOURCE_NAME="projects/<project-number>/locations/<region>/reasoningEngines/<engine-id>"
export AGENT_DIRECTORY="app"
```

### 3. Run Agent via ADK Web Local Development UI
To launch the ADK Playground locally with memory service support:
```bash
uv run adk web . --port 8080 --reload_agents --memory_service_uri=agentengine://<memory-bank-id>
```

### 4. Run Custom FastAPI Web Frontend
To run the lightweight FastAPI proxy and chat UI locally:
```bash
cd frontend
pip install -r requirements.txt
AGENT_ENGINE_RESOURCE_NAME=$AGENT_ENGINE_RESOURCE_NAME AGENT_DIRECTORY=$AGENT_DIRECTORY uvicorn app:app --port 8080 --reload
```

---

## ☁️ Deployment Instructions

### Deploy Agent Engine to Agent Runtime
Deploy the ADK agent using `agents-cli`:
```bash
agents-cli deploy agent_runtime
```

### Deploy Web Frontend to Cloud Run
Deploy the frontend service to Cloud Run:
```bash
cd frontend
gcloud run deploy fitcoach-frontend \
  --source . \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars="AGENT_ENGINE_RESOURCE_NAME=$AGENT_ENGINE_RESOURCE_NAME,AGENT_DIRECTORY=$AGENT_DIRECTORY"
```

---

## 📁 Repository Structure

```
fitcoach-ai/
├── app/
├── README.md
├── agents-cli-manifest.yaml
├── pyproject.toml
├── demo.gif
└── frontend/
    ├── app.py
    ├── Dockerfile
    ├── requirements.txt
    └── static/
        └── index.html
```
