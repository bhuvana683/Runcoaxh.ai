import sys
from google.cloud import firestore

# Hardcoded project ID as required for Agent Platform compatibility
PROJECT_ID = "qwiklabs-gcp-02-760a1240ce59"

def seed_database():
    print(f"Connecting to Firestore for project: {PROJECT_ID}")
    db = firestore.Client(project=PROJECT_ID)

    # Seed Exercises Collection
    exercises_ref = db.collection("exercises")
    sample_exercises = [
        {
            "id": "push_up",
            "name": "Push Up",
            "category": "Bodyweight",
            "target_muscle": "Chest",
            "difficulty": "Beginner",
            "description": "Standard bodyweight exercise targeting chest, shoulders, and triceps."
        },
        {
            "id": "barbell_squat",
            "name": "Barbell Squat",
            "category": "Strength",
            "target_muscle": "Legs",
            "difficulty": "Intermediate",
            "description": "Compound lower body exercise targeting quadriceps, hamstrings, and glutes."
        },
        {
            "id": "pull_up",
            "name": "Pull Up",
            "category": "Bodyweight",
            "target_muscle": "Back",
            "difficulty": "Intermediate",
            "description": "Upper body pull targeting lats, upper back, and biceps."
        },
        {
            "id": "dumbbell_shoulder_press",
            "name": "Dumbbell Shoulder Press",
            "category": "Strength",
            "target_muscle": "Shoulders",
            "difficulty": "Beginner",
            "description": "Overhead dumbbell press targeting anterior and lateral deltoids."
        },
        {
            "id": "deadlift",
            "name": "Conventional Deadlift",
            "category": "Strength",
            "target_muscle": "Full Body",
            "difficulty": "Advanced",
            "description": "Heavy compound pull building posterior chain, hamstrings, and lower back strength."
        }
    ]

    for ex in sample_exercises:
        doc_id = ex.pop("id")
        exercises_ref.document(doc_id).set(ex, merge=True)
        print(f"Seeded exercise: {doc_id} ({ex['name']})")

    # Seed Sample Workout Logs Collection
    workouts_ref = db.collection("workouts")
    sample_workouts = [
        {
            "user_id": "athlete_1",
            "exercise_name": "Push Up",
            "sets": 3,
            "reps": 20,
            "weight_lbs": 0.0,
            "date": "2026-09-23"
        },
        {
            "user_id": "athlete_1",
            "exercise_name": "Barbell Squat",
            "sets": 4,
            "reps": 8,
            "weight_lbs": 185.0,
            "date": "2026-09-23"
        }
    ]

    for workout in sample_workouts:
        workouts_ref.add(workout)
        print(f"Seeded workout log for {workout['user_id']}: {workout['exercise_name']}")

    print("Firestore database seeding completed successfully!")

if __name__ == "__main__":
    seed_database()
