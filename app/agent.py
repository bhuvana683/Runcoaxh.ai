# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
import json
import os
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import firestore, storage
from google.genai import types

try:
    from .a2ui_utils import a2ui_callback
except ImportError:
    from a2ui_utils import a2ui_callback

# Hardcoded project ID and GCS bucket name as required for Agent Platform compatibility
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-760a1240ce59"
GCS_BUCKET_NAME = "fitcoach-ai-media-qwiklabs-gcp-02-760a1240ce59"
db = firestore.Client(project=FIRESTORE_PROJECT_ID)

# Load Agent Engine / sandbox resource name from deployment_metadata.json
DEPLOYMENT_METADATA_PATH = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")
agent_engine_resource_name = f"projects/260213990888/locations/us-east1/reasoningEngines/820563328785973248"
sandbox_resource_name = None

if os.path.exists(DEPLOYMENT_METADATA_PATH):
    try:
        with open(DEPLOYMENT_METADATA_PATH, "r") as f:
            meta = json.load(f)
            agent_engine_resource_name = meta.get("remote_agent_runtime_id", agent_engine_resource_name)
            sandbox_resource_name = meta.get("sandbox_resource_name", None)
    except Exception:
        pass

if sandbox_resource_name:
    code_executor = AgentEngineSandboxCodeExecutor(sandbox_resource_name=sandbox_resource_name)
else:
    code_executor = AgentEngineSandboxCodeExecutor(agent_engine_resource_name=agent_engine_resource_name)


def get_exercises(target_muscle: str = "") -> list[dict]:
    """Look up exercises from the Firestore database, optionally filtered by target muscle group.

    Args:
        target_muscle: Optional muscle group to filter exercises (e.g. 'Chest', 'Legs', 'Back', 'Shoulders').

    Returns:
        List of exercise dictionaries matching the query.
    """
    exercises_ref = db.collection("exercises")
    docs = exercises_ref.stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        data["id"] = doc.id
        if not target_muscle or target_muscle.lower() in data.get("target_muscle", "").lower():
            results.append(data)
    return results


def log_workout(user_id: str, exercise_name: str, sets: int, reps: int, weight_lbs: float = 0.0, date: str = "") -> str:
    """Log a completed workout session into the Firestore database.

    Args:
        user_id: Identifier for the user/athlete.
        exercise_name: Name of the exercise performed (e.g. 'Push Up', 'Barbell Squat').
        sets: Number of completed sets.
        reps: Number of repetitions per set.
        weight_lbs: Weight lifted in pounds (0.0 for bodyweight).
        date: Date of workout in YYYY-MM-DD format (defaults to current date).

    Returns:
        A confirmation message with the logged document ID.
    """
    if not date:
        date = datetime.datetime.now().strftime("%Y-%m-%d")
    workout_data = {
        "user_id": user_id,
        "exercise_name": exercise_name,
        "sets": sets,
        "reps": reps,
        "weight_lbs": weight_lbs,
        "date": date,
    }
    doc_ref = db.collection("workouts").add(workout_data)
    return f"Successfully logged workout for {exercise_name} ({sets} sets x {reps} reps @ {weight_lbs} lbs). Document ID: {doc_ref[1].id}"


def get_workout_history(user_id: str) -> list[dict]:
    """Retrieve logged workout history for a user from Firestore.

    Args:
        user_id: Identifier for the user/athlete.

    Returns:
        List of recorded workout logs for the specified user.
    """
    workouts_ref = db.collection("workouts")
    query = workouts_ref.where("user_id", "==", user_id).stream()
    results = []
    for doc in query:
        data = doc.to_dict()
        data["id"] = doc.id
        results.append(data)
    return results


def calculate_one_rep_max(weight_lbs: float, reps: int) -> dict:
    """Calculate estimated 1-Rep Max (1RM) and percentage working weight targets for strength training.

    Args:
        weight_lbs: Weight lifted in pounds.
        reps: Number of completed repetitions (1 to 30).

    Returns:
        A dictionary containing estimated 1RM and percentage load targets (60%, 70%, 80%, 90%).
    """
    if reps <= 0 or weight_lbs <= 0:
        return {"error": "Weight and reps must be positive numbers."}

    if reps == 1:
        one_rep_max = weight_lbs
    else:
        one_rep_max = weight_lbs * (1 + reps / 30.0)

    one_rep_max = round(one_rep_max, 1)

    return {
        "estimated_1rm_lbs": one_rep_max,
        "working_weight_targets": {
            "90%_heavy": round(one_rep_max * 0.90, 1),
            "80%_hypertrophy": round(one_rep_max * 0.80, 1),
            "70%_endurance": round(one_rep_max * 0.70, 1),
            "60%_warmup": round(one_rep_max * 0.60, 1),
        },
    }


def search_food_nutrition(food_item: str) -> list[dict]:
    """Search Open Food Facts API for food items and retrieve real nutritional facts (calories, protein, carbs, fat per 100g).

    Args:
        food_item: The food item or supplement to query (e.g. 'chicken breast', 'whey protein', 'greek yogurt').

    Returns:
        A list of matching products with nutritional content per 100g.
    """
    # Reads optional API key from environment variable if provided
    api_key = os.getenv("NUTRITION_API_KEY", "")
    headers = {"User-Agent": "FitCoachAI/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    encoded_query = urllib.parse.quote(food_item)
    url = f"https://world.openfoodfacts.org/cgi/search.pl?search_terms={encoded_query}&search_simple=1&action=process&json=1"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            products = data.get("products", [])[:5]
            results = []
            for p in products:
                nutriments = p.get("nutriments", {})
                results.append({
                    "product_name": p.get("product_name", "Unknown Food Item"),
                    "brands": p.get("brands", "N/A"),
                    "calories_100g": nutriments.get("energy-kcal_100g") or nutriments.get("energy-kcal_value", "N/A"),
                    "proteins_100g": nutriments.get("proteins_100g", "N/A"),
                    "carbs_100g": nutriments.get("carbohydrates_100g", "N/A"),
                    "fats_100g": nutriments.get("fat_100g", "N/A"),
                })
            return results
    except Exception as e:
        return [{"error": f"Failed to fetch nutrition data for {food_item}: {str(e)}"}]


def geocode_address(address: str) -> dict:
    """Turn an address or location name into geographic coordinates using the Google Maps Geocoding API.

    Args:
        address: The address, city, or location name to geocode (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA' or 'San Francisco, CA').

    Returns:
        A dictionary containing key fields: name, address, and location coordinates (latitude and longitude).
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return {"error": "GOOGLE_MAPS_API_KEY environment variable is not configured with a valid API key."}

    encoded_address = urllib.parse.quote(address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"

    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            results = data.get("results", [])
            if not results:
                return {"error": f"No geocoding results found for address: {address}"}
            first = results[0]
            loc = first.get("geometry", {}).get("location", {})
            return {
                "name": address,
                "address": first.get("formatted_address", address),
                "location": {
                    "latitude": loc.get("lat"),
                    "longitude": loc.get("lng"),
                },
            }
    except Exception as e:
        return {"error": f"Geocoding API request failed: {str(e)}"}


def find_nearby_places(latitude: float, longitude: float, place_type: str = "gym", radius_meters: float = 2000.0) -> list[dict]:
    """Find nearby places (e.g. gyms, parks, sports complexes) around a location using the Google Maps Places API (New).

    Args:
        latitude: Latitude coordinate of center point.
        longitude: Longitude coordinate of center point.
        place_type: Type of place to search for (e.g. 'gym', 'park', 'sports_complex', 'fitness_center').
        radius_meters: Search radius in meters (default 2000.0 meters).

    Returns:
        A list of nearby place dictionaries containing key fields: name, address, and location (latitude and longitude).
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not api_key or api_key == "PASTE_KEY_HERE":
        return [{"error": "GOOGLE_MAPS_API_KEY environment variable is not configured with a valid API key."}]

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
    }
    payload = {
        "includedTypes": [place_type],
        "maxResultCount": 10,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "radius": radius_meters,
            }
        },
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            places_raw = data.get("places", [])
            results = []
            for p in places_raw:
                results.append({
                    "name": p.get("displayName", {}).get("text", "Unknown Place"),
                    "address": p.get("formattedAddress", "N/A"),
                    "location": p.get("location", {}),
                })
            return results
    except Exception as e:
        return [{"error": f"Places API (New) request failed: {str(e)}"}]


async def generate_workout_badge(
    prompt: str,
    tool_context: ToolContext,
) -> dict:
    """Generate a fitness milestone badge or exercise graphic using the gemini-3.1-flash-lite-image model in global region.

    Saves the generated image as an artifact in ADK tool_context (so it appears in Playground Artifacts panel)
    and uploads the image bytes directly to the public Cloud Storage bucket, returning its public https URL.

    Args:
        prompt: Description of the workout badge or fitness graphic to generate (e.g. 'A gold milestone badge for 100 pushups').
        tool_context: ADK ToolContext instance for saving session artifacts.

    Returns:
        A dictionary containing the filename, public Cloud Storage URL (https://storage.googleapis.com/<bucket>/<object>), and status message.
    """
    client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=f"A vibrant high quality fitness milestone badge or workout illustration: {prompt}",
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
            ),
        )

        image_bytes = None
        mime_type = "image/png"
        if response.candidates and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    mime_type = part.inline_data.mime_type or "image/png"
                    break

        if not image_bytes:
            return {"error": "No image data was generated by the model."}

        filename = f"workout_badge_{uuid.uuid4().hex[:8]}.png"

        # 1. Save as artifact in Playground via tool_context
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload image bytes directly to public GCS bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "filename": filename,
            "public_url": public_url,
            "message": f"Successfully generated workout badge '{filename}'."
        }
    except Exception as e:
        return {"error": f"Failed to generate workout badge: {str(e)}"}


async def generate_exercise_video(
    prompt: str,
    tool_context: ToolContext,
) -> dict:
    """Generate a short exercise demonstration or fitness video using Google's Omni model (gemini-omni-flash-preview) in the global region.

    Saves the generated video as an artifact in ADK tool_context (so it appears in Playground Artifacts panel)
    and uploads the video bytes directly to the public Cloud Storage bucket, returning its public https URL.

    Args:
        prompt: Description of the exercise or workout video to generate (e.g. 'A short video demonstration of an athlete performing a bench press with proper form').
        tool_context: ADK ToolContext instance for saving session artifacts.

    Returns:
        A dictionary containing the filename, public Cloud Storage URL (https://storage.googleapis.com/<bucket>/<object>), and status message.
    """
    client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")

    try:
        interaction = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=f"A short video demonstration or exercise guidance video showing: {prompt}"
        )

        video_obj = getattr(interaction, "output_video", None)
        video_bytes = None
        mime_type = "video/mp4"

        if video_obj:
            if hasattr(video_obj, "mime_type") and video_obj.mime_type:
                mime_type = video_obj.mime_type
            if hasattr(video_obj, "data") and video_obj.data:
                if isinstance(video_obj.data, bytes):
                    video_bytes = video_obj.data
                elif isinstance(video_obj.data, str):
                    import base64
                    video_bytes = base64.b64decode(video_obj.data)

        if not video_bytes:
            return {"error": "No video bytes were generated by the model."}

        filename = f"exercise_video_{uuid.uuid4().hex[:8]}.mp4"

        # 1. Save as artifact in Playground via tool_context
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # 2. Upload video bytes directly to public GCS bucket
        storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

        return {
            "status": "success",
            "filename": filename,
            "public_url": public_url,
            "message": f"Successfully generated exercise video '{filename}'."
        }
    except Exception as e:
        return {"error": f"Failed to generate exercise video: {str(e)}"}


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


async def generate_memories_callback(callback_context: CallbackContext):
    """Callback triggered after each turn to extract and persist durable facts to Memory Bank."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:
        pass
    return None


def memory_bank_service_builder():
    """Memory Bank service builder for deployed agent runtime / custom app runners."""
    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT_ID,
        location="us-east1",
        agent_engine_id="820563328785973248",
    )


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are FitCoach AI, a universally intelligent, deeply analytical, and all-knowing AI assistant & expert health coach. "
        "You possess comprehensive knowledge across all domains — computer science, mathematics, general science, philosophy, history, literature, coding, logic, business, creative writing, and everyday problem solving — as well as specialized expertise in health, fitness, strength training, 1RM calculations, nutrition, and wellness. "
        "You NEVER refuse non-fitness queries or restrict yourself strictly to fitness topics. Answer ANY question the user asks with deep intelligence, articulate step-by-step reasoning, and comprehensive detail. "
        "Always pay close attention to, remember, and respect user food allergies, dietary preferences, and personal goals when health or nutrition is discussed."
    ),
    workflow_description=(
        "Help users with ANY query they present — including software engineering, science, mathematics, general trivia, history, philosophy, writing, logic puzzles, OR workout routines, workout logging, progress tracking, 1RM math calculations, nutrition facts, gym discovery, milestone badge generation, exercise video demonstrations, and executing Python code. "
        "When dealing with math, logic, science, or code, show step-by-step thinking and execute code when helpful. "
        "Ensure all diet and meal recommendations strictly adhere to remembered allergies and dietary preferences."
    ),
    ui_description=(
        "For workout routines, 1RM calculations, nutrition tables, or structured summaries, emit clean A2UI JSON components. "
        "For normal conversational queries, general questions, coding, philosophy, science, or math explanations, provide rich, clear prose with step-by-step reasoning. "
        "When generating A2UI: keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use Table or Heading. "
        "You may include one Image component, but only when you have a public https URL for the image (for example the URL an image tool returns after uploading to a public bucket). Set the Image url to that exact https link. Never point an Image at a bare filename or non-http(s) path. "
        "No markdown inside A2UI text; use usageHint ('h1', 'h2', 'body') for headings. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in <a2a_datapart_json> tags."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    code_executor=code_executor,
    tools=[
        PreloadMemoryTool(),
        get_exercises,
        log_workout,
        get_workout_history,
        calculate_one_rep_max,
        search_food_nutrition,
        geocode_address,
        find_nearby_places,
        generate_workout_badge,
        generate_exercise_video,
        get_weather,
        get_current_time,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)

