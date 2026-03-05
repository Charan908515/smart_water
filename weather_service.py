import requests
import time
from typing import Dict, Optional, List
import config

class WeatherService:

    def __init__(self):
        self.cache = {}
        self.geo_cache = {}
        self.cache_duration = config.WEATHER_CACHE_DURATION

    def _is_cache_valid(self, cache: dict, key: str) -> bool:
        if key not in cache:
            return False
        cached_time = cache[key].get('timestamp', 0)
        return (time.time() - cached_time) < self.cache_duration

    def _format_location_label(self, name: str, admin1: str, country: str) -> str:
        parts = [p for p in [name, admin1, country] if p]
        return ", ".join(parts) if parts else name

    def _geocode(self, location: str) -> Optional[dict]:
        if not location:
            return None

        key = location.strip().lower()
        if self._is_cache_valid(self.geo_cache, key):
            return self.geo_cache[key]['data']

        # Open-Meteo works best with just the city name. 
        # If the user enters "Pune, Maharashtra", just extract "Pune".
        search_name = location.split(',')[0].strip()

        params = {
            'name': search_name,
            'count': 5,
            'language': 'en',
            'format': 'json'
        }
        if config.WEATHER_GEO_COUNTRY_CODE:
            params['countryCode'] = config.WEATHER_GEO_COUNTRY_CODE

        response = requests.get('https://geocoding-api.open-meteo.com/v1/search', params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get('results') or []
        if not results:
            return None

        r0 = results[0]
        loc = {
            'name': r0.get('name', ''),
            'admin1': r0.get('admin1', ''),
            'country': r0.get('country', ''),
            'latitude': r0.get('latitude'),
            'longitude': r0.get('longitude')
        }

        self.geo_cache[key] = {
            'data': loc,
            'timestamp': time.time()
        }

        return loc

    def get_location_suggestions(self, query: str, count: int = 6) -> List[dict]:
        if not query or len(query.strip()) < 2:
            return []

        search_name = query.split(',')[0].strip()

        params = {
            'name': search_name,
            'count': count,
            'language': 'en',
            'format': 'json'
        }
        if config.WEATHER_GEO_COUNTRY_CODE:
            params['countryCode'] = config.WEATHER_GEO_COUNTRY_CODE

        response = requests.get('https://geocoding-api.open-meteo.com/v1/search', params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        results = data.get('results') or []

        suggestions = []
        for r in results:
            label = self._format_location_label(r.get('name', ''), r.get('admin1', ''), r.get('country', ''))
            if label:
                suggestions.append({
                    'label': label,
                    'value': label
                })

        return suggestions

    def get_weather(self, location: str) -> Dict:
        if self._is_cache_valid(self.cache, location):
            return self.cache[location]['data']

        try:
            loc = self._geocode(location)
            if not loc:
                return {
                    'success': False,
                    'error': 'Location not found',
                    'temperature': 20,
                    'condition': 'Normal',
                    'description': 'Location not found - using default values',
                    'humidity': 50
                }

            params = {
                'latitude': loc['latitude'],
                'longitude': loc['longitude'],
                'current_weather': 'true',
                'hourly': 'relative_humidity_2m',
                'timezone': 'auto'
            }

            response = requests.get('https://api.open-meteo.com/v1/forecast', params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            current = data.get('current_weather', {})
            temp = current.get('temperature', 20)
            weathercode = current.get('weathercode', None)
            description = self._weather_description(weathercode)

            humidity = 50
            try:
                hourly = data.get('hourly', {})
                times = hourly.get('time', [])
                hums = hourly.get('relative_humidity_2m', [])
                current_time = current.get('time')
                if current_time in times:
                    idx = times.index(current_time)
                    humidity = hums[idx]
                elif hums:
                    humidity = hums[0]
            except Exception:
                pass

            condition = self._classify_temperature(temp)
            location_label = self._format_location_label(loc.get('name', ''), loc.get('admin1', ''), loc.get('country', ''))

            weather_data = {
                'success': True,
                'temperature': round(temp, 1),
                'condition': condition,
                'description': description,
                'humidity': humidity,
                'location': location_label
            }

            self.cache[location] = {
                'data': weather_data,
                'timestamp': time.time()
            }

            return weather_data

        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': str(e),
                'temperature': 20,
                'condition': 'Normal',
                'description': f'Error fetching weather: {str(e)}',
                'humidity': 50
            }

    def _classify_temperature(self, temp: float) -> str:
        if temp >= config.TEMP_HOT_THRESHOLD:
            return 'Hot'
        if temp <= config.TEMP_COLD_THRESHOLD:
            return 'Cold'
        return 'Normal'

    def _weather_description(self, code: Optional[int]) -> str:
        mapping = {
            0: 'Clear sky',
            1: 'Mainly clear',
            2: 'Partly cloudy',
            3: 'Overcast',
            45: 'Fog',
            48: 'Depositing rime fog',
            51: 'Light drizzle',
            53: 'Moderate drizzle',
            55: 'Dense drizzle',
            61: 'Slight rain',
            63: 'Moderate rain',
            65: 'Heavy rain',
            71: 'Slight snow fall',
            73: 'Moderate snow fall',
            75: 'Heavy snow fall',
            80: 'Rain showers',
            81: 'Heavy rain showers',
            82: 'Violent rain showers',
            95: 'Thunderstorm',
            96: 'Thunderstorm with hail',
            99: 'Thunderstorm with heavy hail'
        }
        return mapping.get(code, 'Unknown')

    def get_weather_by_coords(self, latitude: float, longitude: float) -> Dict:
        """Fetch weather directly from latitude/longitude without geocoding."""
        cache_key = f"{round(latitude, 4)},{round(longitude, 4)}"
        if self._is_cache_valid(self.cache, cache_key):
            return self.cache[cache_key]['data']

        try:
            params = {
                'latitude': latitude,
                'longitude': longitude,
                'current_weather': 'true',
                'hourly': 'relative_humidity_2m',
                'timezone': 'auto'
            }

            response = requests.get('https://api.open-meteo.com/v1/forecast', params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            current = data.get('current_weather', {})
            temp = current.get('temperature', 20)
            weathercode = current.get('weathercode', None)
            description = self._weather_description(weathercode)

            humidity = 50
            try:
                hourly = data.get('hourly', {})
                times = hourly.get('time', [])
                hums = hourly.get('relative_humidity_2m', [])
                current_time = current.get('time')
                if current_time in times:
                    idx = times.index(current_time)
                    humidity = hums[idx]
                elif hums:
                    humidity = hums[0]
            except Exception:
                pass

            condition = self._classify_temperature(temp)

            weather_data = {
                'success': True,
                'temperature': round(temp, 1),
                'condition': condition,
                'description': description,
                'humidity': humidity,
                'latitude': latitude,
                'longitude': longitude,
                'location': f"{round(latitude, 4)}, {round(longitude, 4)}"
            }

            self.cache[cache_key] = {
                'data': weather_data,
                'timestamp': time.time()
            }

            return weather_data

        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': str(e),
                'temperature': 20,
                'condition': 'Normal',
                'description': f'Error fetching weather: {str(e)}',
                'humidity': 50
            }

    def get_weather_adjustment_factor(self, location: str) -> float:
        weather = self.get_weather(location)
        condition = weather.get('condition', 'Normal')
        return config.WEATHER_ADJUSTMENT.get(condition, 1.0)


_weather_service = None


def get_weather_service() -> WeatherService:
    global _weather_service
    if _weather_service is None:
        _weather_service = WeatherService()
    return _weather_service


if __name__ == "__main__":
    print("=" * 60)
    print("WEATHER SERVICE TEST")
    print("=" * 60)

    service = get_weather_service()

    test_location = "Pune"
    print(f"\nTesting weather for: {test_location}")

    weather = service.get_weather(test_location)

    if weather['success']:
        print("Weather fetched successfully")
        print(f"Location: {weather.get('location', test_location)}")
        print(f"Temperature: {weather['temperature']} C")
        print(f"Condition: {weather['condition']}")
        print(f"Description: {weather['description']}")
        print(f"Humidity: {weather['humidity']}%")
        print(f"Adjustment Factor: {service.get_weather_adjustment_factor(test_location)}")
    else:
        print(f"Error: {weather.get('error', 'Unknown error')}")
        print(f"Using defaults: {weather['condition']} ({weather['temperature']} C)")
