from fastapi import FastAPI, HTTPException, Query, Response, Cookie
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from hydration_predictor import HydrationPredictor
from weather_service import get_weather_service
from user_profile import UserProfile, find_profile_by_mac, find_profile_by_username, normalize_mac_id
import uvicorn
import asyncio
import os

app = FastAPI(
    title="Hydration Predictor API",
    description="API for predicting hydration risk levels",
    version="2.0.0"
)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), 'static')
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

try:
    predictor = HydrationPredictor()
except Exception as e:
    predictor = None
    print(f"Warning: Failed to load predictor model: {e}")



async def hourly_weather_task():
    """Background task: fetch weather for all registered users every hour."""
    while True:
        try:
            from database import get_db
            db = get_db()
            if db is None:
                await asyncio.sleep(3600)
                continue

            users = db.users.find(
                {'mac_id': {'$ne': ''}},
                {'mac_id': 1, 'location': 1, 'coords': 1}
            )
            for user in users:
                try:
                    mac_id = user.get('mac_id', '')
                    if not mac_id:
                        continue
                    profile = find_profile_by_mac(mac_id)
                    if not profile:
                        continue
                    weather = _get_weather_for_profile(profile)
                    if weather.get('success'):
                        profile.add_weather_reading(
                            temperature=weather.get('temperature', 0),
                            condition=weather.get('condition', 'Normal'),
                            humidity=weather.get('humidity', 0)
                        )
                        print(f"[Weather] {mac_id}: {weather.get('temperature')} C")
                except Exception as e:
                    print(f"[Weather] Error for {user.get('mac_id', 'unknown')}: {e}")
        except Exception as e:
            print(f"[Weather Task] Error: {e}")
        await asyncio.sleep(3600)  # every 1 hour


@app.on_event("startup")
async def startup_event():
    """Run background tasks on server startup."""
    # Do an initial weather fetch immediately, then every hour
    asyncio.create_task(hourly_weather_task())



class RegisterRequest(BaseModel):
    mac_id: str = Field(..., description="Full device MAC address")
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    password: str = Field(..., description="User password for dashboard access")
    age: int = Field(..., description="Age in years")
    gender: str = Field(..., description="'Male' or 'Female'")
    weight: float = Field(..., description="Weight in kg")
    location: str = Field(..., description="City name for weather")

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Registered username")
    password: str = Field(..., description="User password for dashboard access")

class PredictionRequest(BaseModel):
    mac_id: str = Field(..., description="Full device MAC address")
    activity_level: float = Field(..., description="Numeric activity level from device")

class LogWaterRequest(BaseModel):
    mac_id: str = Field(..., description="Full device MAC address")
    amount: float = Field(..., description="Water amount in liters")

class UpdateCoordsRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="GPS latitude from browser")
    longitude: float = Field(..., ge=-180, le=180, description="GPS longitude from browser")



def _get_weather_for_profile(profile) -> dict:
    """
    Get current weather for a user profile.
    Priority:
      1. Stored GPS coords (set from browser on page open)
      2. Stored city/location name
      3. Default fallback values
    """
    weather_service = get_weather_service()

    coords = profile.get_coords()
    if coords and coords.get('latitude') is not None and coords.get('longitude') is not None:
        return weather_service.get_weather_by_coords(coords['latitude'], coords['longitude'])

    location = profile.data.get('location', '')
    if location:
        return weather_service.get_weather(location)

    return {
        'success': False,
        'temperature': 20,
        'condition': 'Normal',
        'description': 'No location data available',
        'humidity': 50
    }


# ─── Endpoints ────────────────────────────────────────────────

@app.get("/")
async def serve_index():
    """Serve the main web page."""
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/verify-session")
async def verify_session(session_mac: str = Cookie(None)):
    """Verify if the user has an active 30-day cookie session."""
    if not session_mac:
        raise HTTPException(status_code=401, detail="No active session")
    
    profile = find_profile_by_mac(session_mac)
    if profile is None:
        raise HTTPException(status_code=401, detail="Session invalid")
    
    summary = profile.get_summary()
    summary['has_password'] = profile.has_password()
    return {"mac_id": session_mac, "profile": summary}


@app.get("/device/{mac_id}")
async def check_device(mac_id: str):
    """Check if a device MAC ID is registered. Returns profile summary or 404."""
    profile = find_profile_by_mac(mac_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Device not registered")
    
    summary = profile.get_summary()
    summary['has_password'] = profile.has_password()
    return summary


@app.post("/register")
async def register_user(request: RegisterRequest, response: Response):
    """Register a new user linked to a device MAC ID."""
    mac_clean = normalize_mac_id(request.mac_id)
    if len(mac_clean) < 12:
        raise HTTPException(status_code=400, detail="Please provide the full MAC ID (not partial).")

    # Check if MAC is already registered
    existing = find_profile_by_mac(mac_clean)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Device already registered")
    
    # Check if username is already registered
    existing_username = find_profile_by_username(request.username)
    if existing_username is not None:
        raise HTTPException(status_code=409, detail="Username already registered")

    import uuid
    new_user_id = str(uuid.uuid4())
    
    # Create profile keyed by user_id
    username_clean = request.username.strip().lower()
    profile = UserProfile(new_user_id)
    profile.update_mac_id(mac_clean)
    profile.update_username(username_clean)
    profile.set_password(request.password)
    profile.update_base_info(
        age=request.age,
        gender=request.gender,
        weight=request.weight
    )
    profile.set_location(request.location)
    
    # Set 30-day session cookie
    response.set_cookie(key="session_mac", value=mac_clean, max_age=30*24*60*60, httponly=True)
    
    return {"message": "Registration successful", "profile": profile.get_summary()}


@app.post("/login")
async def login_user(request: LoginRequest, response: Response):
    """Authenticate a returning user with their username and password."""
    profile = find_profile_by_username(request.username)
    if profile is None:
        raise HTTPException(status_code=404, detail="Username not registered")
        
    if not profile.has_password():
        raise HTTPException(status_code=400, detail="Account has no password configured")
        
    if not profile.verify_password(request.password):
        raise HTTPException(status_code=401, detail="Incorrect password")
        
    # Set 30-day session cookie
    response.set_cookie(key="session_mac", value=profile.data.get('mac_id'), max_age=30*24*60*60, httponly=True)
        
    return {"message": "Login successful", "profile": profile.get_summary()}


@app.post("/logout")
async def logout(response: Response):
    """Clear the session cookie to securely log out."""
    response.delete_cookie("session_mac")
    return {"message": "Logged out successfully"}


@app.post("/predict")
async def predict_hydration(request: PredictionRequest):
    """
    Predict hydration risk every time the device sends an activity level.
    - Activity is categorised against the 7-day rolling average (baseline=72
      for the first 7 days so a category is always available).
    - Weather uses GPS coords from the last browser open, then city name, then defaults.
    - Missing profile fields (age/gender/weight) fall back to safe defaults so
      the model ALWAYS runs; `profile_complete` in the response flags this.
    """
    if predictor is None:
        raise HTTPException(
            status_code=500,
            detail="Predictor model is not loaded. Please ensure models are trained."
        )

    mac_clean = normalize_mac_id(request.mac_id)
    profile = find_profile_by_mac(mac_clean)
    if profile is None:
        return {
            "ignored": True,
            "message": "mac_id not registered; activity reading ignored",
            "mac_id": mac_clean
        }

    # Store the activity reading
    profile.add_activity_reading(request.activity_level)

    # Categorise — always returns Low/Moderate/High (uses baseline 72 for first 7 days)
    activity_category = profile.get_activity_category(request.activity_level)

    base_info = profile.data.get('base_info', {})
    has_base = bool(base_info.get('age')) and bool(base_info.get('gender')) and bool(base_info.get('weight'))

    # Use profile values or safe defaults so the model always has valid inputs
    age    = base_info.get('age', 25)
    gender = base_info.get('gender', 'Male')
    weight = base_info.get('weight', 70)

    try:
        # Weather: GPS coords first, then city name, then defaults
        weather_data = _get_weather_for_profile(profile)
        weather_condition = weather_data.get('condition', 'Normal')

        print(f"\n[ML Predictor] Running model for /predict (MAC: {mac_clean})")
        print(f"   ↳ Inputs -> Age:{age}, Gender:{gender}, Weight:{weight}, Activity:{activity_category}, Weather:{weather_condition}, Water:{profile.get_today_water_intake()}L")

        result = predictor.predict(
            age=age,
            gender=gender,
            weight=weight,
            activity_level=activity_category,
            weather=weather_condition,
            water_intake=profile.get_today_water_intake()
        )

        result["profile_complete"]    = has_base
        result["activity_category"]   = activity_category
        result["activity_7day_avg"]   = profile.get_7day_activity_average()
        result["activity_current"]    = request.activity_level
        result["weather_used"]        = weather_data
        result["today_water_intake"]  = profile.get_today_water_intake()
        result["recommended_intake"]  = profile.get_recommended_intake()

        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")



@app.post("/log-water")
async def log_water(request: LogWaterRequest):
    """Log a water intake event and instantly return the new ML prediction."""
    mac_clean = normalize_mac_id(request.mac_id)
    profile = find_profile_by_mac(mac_clean)
    if profile is None:
        raise HTTPException(status_code=404, detail="Device not registered")

    profile.log_water(request.amount)
    
    # Run the ML Predictor with the newly logged water!
    prediction = None
    if predictor is not None:
        try:
            base_info = profile.data.get('base_info', {})
            activity_category = profile.get_activity_category()
            
            # Weather
            try:
                weather_data = _get_weather_for_profile(profile)
                weather_condition = weather_data.get('condition', 'Normal') if weather_data and weather_data.get('success') else 'Normal'
            except Exception:
                weather_condition = 'Normal'

            print(f"\n[ML Predictor] Running model for /log-water (MAC: {mac_clean})")
            print(f"   ↳ Inputs -> Age:{base_info.get('age', 25)}, Gender:{base_info.get('gender', 'Male')}, Weight:{base_info.get('weight', 70)}, Activity:{activity_category if activity_category else 'Low'}, Weather:{weather_condition}, Water:{profile.get_today_water_intake()}L")

            prediction = predictor.predict(
                age=base_info.get('age', 25),
                gender=base_info.get('gender', 'Male'),
                weight=base_info.get('weight', 70),
                activity_level=activity_category if activity_category else 'Low',
                weather=weather_condition,
                water_intake=profile.get_today_water_intake()
            )
        except Exception as e:
            print(f"[Log Water Prediction Error] {e}")

    return {
        "message": "Water logged",
        "today_total": profile.get_today_water_intake(),
        "recommended": profile.get_recommended_intake(),
        "prediction": prediction
    }


@app.put("/coords/{mac_id}")
async def update_coords(mac_id: str, request: UpdateCoordsRequest):
    """
    Store the user's GPS coordinates from the browser.
    Called automatically on page open; used by the server for all subsequent
    weather lookups (activity pings, hourly task, predictions).
    """
    mac_clean = normalize_mac_id(mac_id)
    profile = find_profile_by_mac(mac_clean)
    if profile is None:
        raise HTTPException(status_code=404, detail="Device not registered")

    profile.set_coords(request.latitude, request.longitude)
    return {
        "message": "Location updated",
        "latitude": request.latitude,
        "longitude": request.longitude
    }


@app.get("/status/{mac_id}")
async def get_status(mac_id: str):
    """Get full current hydration status for a device."""
    mac_clean = normalize_mac_id(mac_id)
    profile = find_profile_by_mac(mac_clean)
    if profile is None:
        raise HTTPException(status_code=404, detail="Device not registered")

    summary = profile.get_summary()

    base_info = profile.data.get('base_info', {})
    activity_category = profile.get_activity_category()

    # Use GPS coords (from last browser open) first; fall back to city name
    try:
        weather_data = _get_weather_for_profile(profile)
        if not weather_data.get('success'):
            weather_data = None
    except Exception:
        weather_data = None

    # Only run prediction if predictor is available
    if predictor is not None:
        try:
            # Use profile values or safe defaults (so model always runs)
            age    = base_info.get('age', 25)
            gender = base_info.get('gender', 'Male')
            weight = base_info.get('weight', 70)
            
            # Use Low if activity category somehow missing
            act_cat = activity_category if activity_category else 'Low'
            
            # Use Normal if weather_data is None
            weather_condition = weather_data.get('condition', 'Normal') if weather_data else 'Normal'

            prediction = predictor.predict(
                age=age,
                gender=gender,
                weight=weight,
                activity_level=act_cat,
                weather=weather_condition,
                water_intake=profile.get_today_water_intake()
            )
            summary["prediction"] = prediction
        except Exception as e:
            print(f"[Status Prediction Error] {e}")
            summary["prediction"] = None
    else:
        summary["prediction"] = None

    summary["weather"] = weather_data

    return summary


@app.get("/weather-history/{mac_id}")
async def get_weather_history(mac_id: str, hours: int = 24):
    """Get hourly weather temperature readings for a device's location."""
    mac_clean = normalize_mac_id(mac_id)
    profile = find_profile_by_mac(mac_clean)
    if profile is None:
        raise HTTPException(status_code=404, detail="Device not registered")
    return {
        "mac_id": mac_clean,
        "location": profile.data.get('location', ''),
        "readings": profile.get_weather_history(hours)
    }


@app.get("/weather-by-coords")
async def weather_by_coords(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lon: float = Query(..., ge=-180, le=180, description="Longitude")
):
    """Get current weather for GPS coordinates (browser geolocation)."""
    weather_service = get_weather_service()
    try:
        result = weather_service.get_weather_by_coords(lat, lon)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Weather fetch failed: {str(e)}")


@app.get("/location-suggest")
async def location_suggest(query: str = Query(..., min_length=2, max_length=60)):
    """Suggest location names supported by the weather provider."""
    weather_service = get_weather_service()
    try:
        results = weather_service.get_location_suggestions(query)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Location lookup failed: {str(e)}")


@app.get("/activity-history/{mac_id}")
async def get_activity_history(mac_id: str, count: int = 20):
    """Get raw activity level values received from the device."""
    mac_clean = normalize_mac_id(mac_id)
    profile = find_profile_by_mac(mac_clean)
    if profile is None:
        raise HTTPException(status_code=404, detail="Device not registered")
    return {
        "mac_id": mac_clean,
        "readings": profile.get_raw_activity_values(count),
        "category": profile.get_activity_category(),
        "avg_7day": profile.get_7day_activity_average()
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy" if predictor is not None else "degraded",
        "model_loaded": predictor is not None
    }


if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
