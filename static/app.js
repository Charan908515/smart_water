/* ===================================================================
   Smart Water – Frontend Application
   Auto-detects user location on page-open via Geolocation API,
   caches coords + weather in localStorage for the session.
   =================================================================== */

// ─── State ──────────────────────────────────────────────────────────
let currentMac = null;
let dashboardTimer = null;

// Keys used in localStorage
const LS_COORDS = 'sw_coords';          // { lat, lon, timestamp }
const LS_WEATHER = 'sw_weather_cache';  // weather object + timestamp
const LS_SESSION = 'sw_session_mac';    // current logged-in MAC ID

// How long the geo + weather cache is considered fresh (1 hour in ms)
const GEO_CACHE_MS = 60 * 60 * 1000;
const WEATHER_CACHE_MS = 60 * 60 * 1000;

// ─── Geolocation helpers ─────────────────────────────────────────────

/**
 * Try to load cached coords from localStorage.
 * Returns { lat, lon } if fresh, or null.
 */
function getCachedCoords() {
    try {
        const raw = localStorage.getItem(LS_COORDS);
        if (!raw) return null;
        const { lat, lon, timestamp } = JSON.parse(raw);
        if (Date.now() - timestamp < GEO_CACHE_MS) {
            return { lat, lon };
        }
    } catch (_) { }
    return null;
}

/**
 * Save coords to localStorage with current timestamp.
 */
function saveCoords(lat, lon) {
    localStorage.setItem(LS_COORDS, JSON.stringify({ lat, lon, timestamp: Date.now() }));
}

/**
 * Try to load cached weather from localStorage.
 * Returns the weather object if fresh, or null.
 */
function getCachedWeather() {
    try {
        const raw = localStorage.getItem(LS_WEATHER);
        if (!raw) return null;
        const { data, timestamp } = JSON.parse(raw);
        if (Date.now() - timestamp < WEATHER_CACHE_MS) {
            return data;
        }
    } catch (_) { }
    return null;
}

/**
 * Save weather data to localStorage with current timestamp.
 */
function saveWeatherCache(data) {
    localStorage.setItem(LS_WEATHER, JSON.stringify({ data, timestamp: Date.now() }));
}

/**
 * Fetch weather from backend using GPS coordinates.
 * Stores result in localStorage cache.
 */
async function fetchWeatherByCoords(lat, lon) {
    try {
        const resp = await fetch(`/weather-by-coords?lat=${lat}&lon=${lon}`);
        if (!resp.ok) return null;
        const data = await resp.json();
        if (data.success) {
            saveWeatherCache(data);
        }
        return data;
    } catch (_) {
        return null;
    }
}

/**
 * Main auto-geolocation routine called on page load.
 * 1. Check localStorage for cached weather (still fresh? use it directly)
 * 2. Check localStorage for cached coords (still fresh? re-fetch weather with them)
 * 3. Otherwise ask the browser for position, save coords, fetch weather.
 *
 * The result is stored in `window._autoWeather` and used when rendering
 * the dashboard weather card if the user has no stored location.
 */
async function initAutoGeolocation() {
    // If we already have a fresh weather cache, use it immediately
    const cachedWeather = getCachedWeather();
    if (cachedWeather) {
        window._autoWeather = cachedWeather;
        return;
    }

    // If we have cached coords, fetch new weather (old weather expired but coords OK)
    const cachedCoords = getCachedCoords();
    if (cachedCoords) {
        const weather = await fetchWeatherByCoords(cachedCoords.lat, cachedCoords.lon);
        window._autoWeather = weather;
        return;
    }

    // No cached data – request geolocation from the browser
    if (!navigator.geolocation) return;

    navigator.geolocation.getCurrentPosition(
        async (pos) => {
            const lat = pos.coords.latitude;
            const lon = pos.coords.longitude;
            saveCoords(lat, lon);
            const weather = await fetchWeatherByCoords(lat, lon);
            window._autoWeather = weather;

            // Push fresh coords to server if the user is already logged in
            if (currentMac) {
                pushCoordsToServer(currentMac, lat, lon);
            }

            // If dashboard is already open, update the weather card live
            if (document.getElementById('view-dashboard').classList.contains('active')) {
                renderAutoWeatherCard(weather);
            }
        },
        (_err) => {
            // User denied or error – silently fall back
        },
        { enableHighAccuracy: false, timeout: 8000, maximumAge: GEO_CACHE_MS }
    );
}

/**
 * Push the current GPS coordinates to the backend so the server can use
 * them for activity-based weather lookups until the user opens the site again.
 */
async function pushCoordsToServer(mac, lat, lon) {
    try {
        await fetch(`/coords/${mac}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ latitude: lat, longitude: lon })
        });
    } catch (_) {
        // Silent – non-critical
    }
}

/**
 * Render auto-detected weather into the dashboard weather stat card.
 * Only called when the profile has no stored location (fallback mode).
 */
function renderAutoWeatherCard(w) {
    if (!w || !w.success) return;
    const val = document.getElementById('stat-weather-val');
    const sub = document.getElementById('stat-weather-sub');
    if (val) val.textContent = `${w.temperature}°C`;
    if (sub) sub.textContent = `${w.description} · ${w.humidity}% RH (GPS)`;

    const card = document.getElementById('stat-weather');
    if (card) {
        card.classList.remove('weather-hot', 'weather-cold');
        if (w.condition === 'Hot') card.classList.add('weather-hot');
        if (w.condition === 'Cold') card.classList.add('weather-cold');
    }
}

// ─── View helpers ────────────────────────────────────────────────────

function showView(name) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    const el = document.getElementById(`view-${name}`);
    if (el) el.classList.add('active');
}

function setLoading(btnId, loading) {
    const btn = document.getElementById(btnId);
    if (!btn) return;
    btn.querySelector('.btn-text').hidden = loading;
    btn.querySelector('.btn-loader').hidden = !loading;
    btn.disabled = loading;
}

function showError(elId, msg) {
    const el = document.getElementById(elId);
    if (!el) return;
    el.textContent = msg;
    el.hidden = false;
}

function clearError(elId) {
    const el = document.getElementById(elId);
    if (el) el.hidden = true;
}

// ─── Device connect ───────────────────────────────────────────────────

async function connectDevice() {
    const mac = document.getElementById('mac-input').value.trim().toUpperCase();
    if (mac.length !== 6) { showError('landing-error', 'Please enter exactly 6 characters.'); return; }
    clearError('landing-error');
    setLoading('btn-connect', true);

    try {
        const resp = await fetch(`/device/${mac}`);
        if (resp.status === 404) {
            // New device – go to registration
            currentMac = mac;
            document.getElementById('reg-mac-badge').textContent = mac;
            showView('register');
        } else if (resp.ok) {
            const data = await resp.json();
            currentMac = mac;
            if (!data.has_password) {
                document.getElementById('setpass-mac-badge').textContent = mac;
                showView('set-password');
            } else {
                document.getElementById('login-mac-badge').textContent = mac;
                showView('login');
            }
        } else {
            showError('landing-error', 'Connection failed. Please try again.');
        }
    } catch (_) {
        showError('landing-error', 'Network error. Is the server running?');
    } finally {
        setLoading('btn-connect', false);
    }
}

// ─── Registration ─────────────────────────────────────────────────────

// Location autocomplete
let locDebounce = null;
document.addEventListener('DOMContentLoaded', () => {
    const locInput = document.getElementById('reg-location');
    if (locInput) {
        locInput.addEventListener('input', () => {
            clearTimeout(locDebounce);
            const q = locInput.value.trim();
            if (q.length < 2) return;
            locDebounce = setTimeout(() => fetchLocationSuggestions(q), 300);
        });
    }
});

async function fetchLocationSuggestions(query) {
    try {
        const resp = await fetch(`/location-suggest?query=${encodeURIComponent(query)}`);
        if (!resp.ok) return;
        const data = await resp.json();
        const dl = document.getElementById('location-suggestions');
        if (!dl) return;
        dl.innerHTML = '';
        (data.results || []).forEach(s => {
            const opt = document.createElement('option');
            opt.value = s.value;
            dl.appendChild(opt);
        });
    } catch (_) { }
}

async function registerUser(event) {
    event.preventDefault();
    clearError('register-error');
    setLoading('btn-register', true);

    const password = document.getElementById('reg-password').value;
    const age = parseInt(document.getElementById('reg-age').value, 10);
    const gender = document.getElementById('reg-gender').value;
    const weight = parseFloat(document.getElementById('reg-weight').value);
    const location = document.getElementById('reg-location').value.trim();

    try {
        const resp = await fetch('/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mac_id: currentMac, password, age, gender, weight, location })
        });
        const data = await resp.json();
        if (resp.ok) {
            openDashboard(data.profile);
        } else {
            showError('register-error', data.detail || 'Registration failed.');
        }
    } catch (_) {
        showError('register-error', 'Network error. Please try again.');
    } finally {
        setLoading('btn-register', false);
    }
}

// ─── Login ────────────────────────────────────────────────────────────

async function loginUser(event) {
    event.preventDefault();
    clearError('login-error');
    setLoading('btn-login', true);

    const password = document.getElementById('login-password').value;

    try {
        const resp = await fetch('/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mac_id: currentMac, password })
        });
        const data = await resp.json();
        if (resp.ok) {
            openDashboard(data.profile);
        } else {
            showError('login-error', data.detail || 'Login failed.');
        }
    } catch (_) {
        showError('login-error', 'Network error. Please try again.');
    } finally {
        setLoading('btn-login', false);
    }
}

// ─── Set password (legacy) ────────────────────────────────────────────

async function setLegacyPassword(event) {
    event.preventDefault();
    clearError('setpass-error');
    setLoading('btn-setpass', true);

    const password = document.getElementById('new-password').value;

    try {
        const resp = await fetch('/set-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mac_id: currentMac, password })
        });
        const data = await resp.json();
        if (resp.ok) {
            openDashboard(data.profile);
        } else {
            showError('setpass-error', data.detail || 'Failed to set password.');
        }
    } catch (_) {
        showError('setpass-error', 'Network error. Please try again.');
    } finally {
        setLoading('btn-setpass', false);
    }
}

// ─── Dashboard ────────────────────────────────────────────────────────

function openDashboard(profile) {
    const info = document.getElementById('dash-user-info');
    const badge = document.getElementById('dash-device-badge');
    if (info) {
        const b = profile.base_info || {};
        info.textContent = [b.gender, b.age ? `${b.age} yrs` : '', b.weight ? `${b.weight} kg` : '']
            .filter(Boolean).join(' · ');
    }
    if (badge) badge.textContent = currentMac;

    // Save session so refresh doesn't require re-login
    localStorage.setItem(LS_SESSION, currentMac);

    showView('dashboard');
    refreshDashboard();
    if (dashboardTimer) clearInterval(dashboardTimer);
    dashboardTimer = setInterval(refreshDashboard, 30000);

    // Push GPS coords to server so device pings can use the correct location
    const coords = getCachedCoords();
    if (coords) {
        pushCoordsToServer(currentMac, coords.lat, coords.lon);
    }
}

async function refreshDashboard() {
    if (!currentMac) return;

    try {
        const resp = await fetch(`/status/${currentMac}`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderDashboard(data);
    } catch (_) { }

    // Load history sections in parallel
    loadWeatherHistory();
    loadActivityHistory();
}

function renderDashboard(data) {
    // ── Water intake ──────────────────────────────────────────
    const intake = data.today_water_intake ?? 0;
    const recommended = data.recommended_intake ?? 2.0;
    // Remove the 100% cap so the bar can go past the target
    const pct = (intake / recommended) * 100;

    const fill = document.getElementById('water-fill');
    const cur = document.getElementById('water-current');
    const tgt = document.getElementById('water-target');
    const pctEl = document.getElementById('water-percent');

    if (fill) fill.style.width = `${pct}%`;
    if (cur) cur.textContent = `${intake.toFixed(2)} L`;
    if (tgt) tgt.textContent = ``; // Hide the target/limit text
    if (pctEl) pctEl.textContent = ``; // Hide the percentage text

    // ── Weather card ──────────────────────────────────────────
    const weatherVal = document.getElementById('stat-weather-val');
    const weatherSub = document.getElementById('stat-weather-sub');
    const weatherCard = document.getElementById('stat-weather');

    let weatherRendered = false;

    if (data.weather && data.weather.success) {
        const w = data.weather;
        if (weatherVal) weatherVal.textContent = `${w.temperature}°C`;
        if (weatherSub) weatherSub.textContent = `${w.description} · ${w.humidity}% RH`;
        if (weatherCard) {
            weatherCard.classList.remove('weather-hot', 'weather-cold');
            if (w.condition === 'Hot') weatherCard.classList.add('weather-hot');
            if (w.condition === 'Cold') weatherCard.classList.add('weather-cold');
        }
        weatherRendered = true;
    }

    // Fallback: use auto-detected GPS weather
    if (!weatherRendered && window._autoWeather) {
        renderAutoWeatherCard(window._autoWeather);
    } else if (!weatherRendered) {
        if (weatherVal) weatherVal.textContent = '—';
        if (weatherSub) weatherSub.textContent = 'Set your location to enable weather';
    }

    // ── Activity card ─────────────────────────────────────────
    const actCat = data.activity_category;
    const actAvg = data.activity_7day_avg;
    const actVal = document.getElementById('stat-activity-val');
    const actSub = document.getElementById('stat-activity-sub');

    if (actVal) actVal.textContent = actCat || '—';
    if (actSub) actSub.textContent = actAvg != null ? `7-day avg: ${actAvg.toFixed(1)}` : 'No readings yet';

    // ── Hydration status card ─────────────────────────────────
    const hydVal = document.getElementById('stat-hydration-val');
    const hydSub = document.getElementById('stat-hydration-sub');
    const pred = data.prediction;
    if (pred) {
        if (hydVal) hydVal.textContent = pred.hydration_status || '—';
        if (hydSub) hydSub.textContent = pred.recommendation || '';
    } else {
        if (hydVal) hydVal.textContent = '—';
        if (hydSub) hydSub.textContent = 'Complete a device sync for prediction';
    }

    // ── Prediction detail ────────────────────────────────────
    const predDetail = document.getElementById('prediction-detail');
    if (predDetail && pred && Object.keys(pred).length > 0) {
        predDetail.innerHTML = `
            <div class="pred-row"><span>Risk Level</span><strong>${pred.risk_level ?? '—'}</strong></div>
            <div class="pred-row"><span>Hydration Status</span><strong>${pred.hydration_status ?? '—'}</strong></div>
            <div class="pred-row"><span>Recommendation</span><em>${pred.recommendation ?? '—'}</em></div>
        `;
    }

    // ── Recommendation banner ─────────────────────────────────
    const recSection = document.getElementById('recommendation-section');
    const recIcon = document.getElementById('rec-icon');
    const recText = document.getElementById('rec-text');
    if (pred && pred.risk_level) {
        const risk = pred.risk_level.toLowerCase();
        if (recSection) recSection.hidden = false;
        if (recIcon) recIcon.textContent = risk === 'high' ? '⚠️' : risk === 'medium' ? '💧' : '✅';
        if (recText) recText.textContent = pred.recommendation || '';
    } else {
        if (recSection) recSection.hidden = true;
    }
}

// ─── Water logging ────────────────────────────────────────────────────

async function logWater(amount) {
    if (!currentMac) return;
    try {
        const resp = await fetch('/log-water', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mac_id: currentMac, amount })
        });
        if (resp.ok) refreshDashboard();
    } catch (_) { }
}

async function logCustomWater() {
    const input = document.getElementById('custom-water-amount');
    const amt = parseFloat(input.value);
    if (!amt || amt <= 0) return;
    await logWater(amt);
    input.value = '';
}

// ─── Weather history chart ────────────────────────────────────────────

async function loadWeatherHistory() {
    if (!currentMac) return;
    try {
        const resp = await fetch(`/weather-history/${currentMac}?hours=24`);
        if (!resp.ok) return;
        const { readings } = await resp.json();
        renderWeatherChart(readings);
    } catch (_) { }
}

function renderWeatherChart(readings) {
    const el = document.getElementById('weather-chart');
    if (!el) return;

    if (!readings || readings.length === 0) {
        el.innerHTML = '<p class="muted">Temperature data will appear after the first hourly fetch.</p>';
        return;
    }

    const max = Math.max(...readings.map(r => r.temperature));
    const min = Math.min(...readings.map(r => r.temperature));
    const range = max - min || 1;

    const bars = readings.slice(-24).map(r => {
        const pct = ((r.temperature - min) / range) * 100;
        const time = r.timestamp ? new Date(r.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
        return `<div class="chart-bar-wrap" title="${r.temperature}°C at ${time}">
                    <div class="chart-bar" style="height:${Math.max(10, pct)}%"></div>
                    <div class="chart-label">${r.temperature}°</div>
                </div>`;
    }).join('');

    el.innerHTML = `<div class="chart-bars">${bars}</div>`;
}

// ─── Activity history table ───────────────────────────────────────────

async function loadActivityHistory() {
    if (!currentMac) return;
    try {
        const resp = await fetch(`/activity-history/${currentMac}?count=20`);
        if (!resp.ok) return;
        const data = await resp.json();
        renderActivityTable(data.readings, data.category);
    } catch (_) { }
}

function renderActivityTable(readings, category) {
    const el = document.getElementById('activity-table-wrap');
    if (!el) return;

    if (!readings || readings.length === 0) {
        el.innerHTML = '<p class="muted">No activity readings yet. Data appears when your device syncs.</p>';
        return;
    }

    const rows = readings.map(r => {
        const time = r.timestamp ? new Date(r.timestamp * 1000).toLocaleString() : '—';
        return `<tr><td>${time}</td><td>${r.value?.toFixed(2) ?? r.toFixed?.(2) ?? r}</td></tr>`;
    }).join('');

    el.innerHTML = `
        <table class="activity-table">
            <thead><tr><th>Time</th><th>Activity Value</th></tr></thead>
            <tbody>${rows}</tbody>
        </table>
        ${category ? `<p class="activity-category">Current category: <strong>${category}</strong></p>` : ''}
    `;
}

// ─── Disconnect ───────────────────────────────────────────────────────

async function disconnect() {
    currentMac = null;
    localStorage.removeItem(LS_SESSION);
    if (dashboardTimer) { clearInterval(dashboardTimer); dashboardTimer = null; }
    document.getElementById('mac-input').value = '';

    // Tell the backend to clear the HttpOnly session cookie
    try {
        await fetch('/logout', { method: 'POST' });
    } catch (_) { }

    showView('landing');
}

// ─── Bootstrap ───────────────────────────────────────────────────────

window.addEventListener('DOMContentLoaded', async () => {
    let loggedIn = false;

    // 1. Check for backend HttpOnly cookie session first
    try {
        const resp = await fetch('/verify-session');
        if (resp.ok) {
            const data = await resp.json();
            currentMac = data.mac_id;
            loggedIn = true;
            openDashboard(data.profile);
        }
    } catch (_) { }

    // 2. Fallback: Check for existing localStorage session
    if (!loggedIn) {
        const savedMac = localStorage.getItem(LS_SESSION);
        if (savedMac) {
            try {
                const resp = await fetch(`/device/${savedMac}`);
                if (resp.ok) {
                    const data = await resp.json();
                    currentMac = savedMac;
                    openDashboard(data);
                }
            } catch (_) { }
        }
    }

    // Kick off silent geolocation immediately when the page opens
    initAutoGeolocation();
});
