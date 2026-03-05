import streamlit as st
from user_profile import UserProfile
from weather_service import get_weather_service
import config

st.set_page_config(
    page_title="Smart Water Intake",
    layout="centered"
)

st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1E88E5;
        text-align: center;
        margin-bottom: 1rem;
    }
    .status-good {
        background: linear-gradient(135deg, #4CAF50, #45a049);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        text-align: center;
        font-size: 1.5rem;
    }
    .status-low {
        background: linear-gradient(135deg, #FF9800, #F57C00);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        text-align: center;
        font-size: 1.5rem;
    }
    .status-critical {
        background: linear-gradient(135deg, #F44336, #D32F2F);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        text-align: center;
        font-size: 1.5rem;
    }
</style>
""", unsafe_allow_html=True)


def get_sweat_calibration_data(profile):
    """Get sweat calibration data from profile"""
    return profile.data.get('sweat_calibration', {
        'is_calibrated': False,
        'daily_readings': [],
        'average_sweat': None
    })


def determine_activity_level(current_sweat, average_sweat):
    """Determine activity level based on sweat vs average"""
    if current_sweat < average_sweat:
        return "Low"
    elif current_sweat > average_sweat:
        return "High"
    else:
        return "Moderate"


def calculate_hydration_status(current_intake, recommended_intake):
    percentage = (current_intake / recommended_intake) * 100
    
    if percentage >= 100:
        return "Well Hydrated", percentage
    elif percentage >= 70:
        return "Good", percentage
    elif percentage >= 50:
        return "Low", percentage
    else:
        return "Critical", percentage


def main():
    st.markdown('<h1 class="main-header"> Smart Water Intake</h1>', unsafe_allow_html=True)
    
    # Sidebar - User Profile
    with st.sidebar:
        st.header(" User Profile")
        user_id = st.text_input("User ID", value="default_user")
        
        if user_id:
            if 'current_user' not in st.session_state or st.session_state.current_user != user_id:
                st.session_state.current_user = user_id
                st.session_state.user_profile = UserProfile(user_id)
            
            profile = st.session_state.user_profile
            base_info = profile.data.get('base_info', {})
            
            if base_info.get('weight'):
                st.success(f" {base_info.get('gender')}, {base_info.get('age')}y, {base_info.get('weight')}kg")
                st.info(f" {profile.data.get('location', 'Not set')}")
            else:
                st.warning(" Complete profile below")
            
            # Calibration status
            cal_data = get_sweat_calibration_data(profile)
            if cal_data['is_calibrated']:
                st.success(f" Avg Sweat: {cal_data['average_sweat']}")
            else:
                days = len(cal_data['daily_readings'])
                st.info(f" Calibration: {days}/7 days")
    
    # Main tabs
    tab1, tab2, tab3 = st.tabs([" Today", " Setup", " Calibration"])
    
    # Tab 1: Today's Hydration
    with tab1:
        st.subheader("Today's Hydration Status")
        
        profile = st.session_state.get('user_profile')
        if not profile:
            st.warning("Select a user ID in sidebar")
        elif not profile.data.get('base_info', {}).get('weight'):
            st.warning(" Complete your profile in Setup tab first")
        else:
            cal_data = get_sweat_calibration_data(profile)
            if not cal_data['is_calibrated']:
                st.warning(" Complete 7-day calibration first (Calibration tab)")
            else:
                base_info = profile.data.get('base_info', {})
                
                # Get weather
                location = profile.data.get('location', 'New York')
                weather_service = get_weather_service()
                weather = weather_service.get_weather(location)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(" Temperature", f"{weather.get('temperature', 'N/A')}°C")
                with col2:
                    st.metric(" Weather", weather.get('condition', 'N/A'))
                
                st.markdown("---")
                
                col1, col2 = st.columns(2)
                with col1:
                    current_sweat = st.number_input(
                        "Current Sweat Reading",
                        min_value=0.0,
                        max_value=100.0,
                        value=cal_data['average_sweat'],
                        step=0.1
                    )
                
                with col2:
                    current_intake = st.number_input(
                        "Water Intake Today (liters)",
                        min_value=0.0,
                        max_value=10.0,
                        value=0.0,
                        step=0.1
                    )
                
                
                weight = base_info['weight']
                recommended = weight * 0.033
                
            
                weather_factor = config.WEATHER_ADJUSTMENT.get(weather.get('condition', 'Normal'), 1.0)
                recommended *= weather_factor
                
                
                activity = determine_activity_level(current_sweat, cal_data['average_sweat'])
                
                
                activity_factor = config.ACTIVITY_ADJUSTMENT.get(activity, 1.0)
                recommended *= activity_factor
                
                
                status, percentage = calculate_hydration_status(current_intake, recommended)
                
                st.markdown("---")
                
                
                status_class = {
                    "Well Hydrated": "status-good",
                    "Good": "status-good",
                    "Low": "status-low",
                    "Critical": "status-critical"
                }
                
                st.markdown(f'<div class="{status_class.get(status, "status-good")}">{status}<br>{percentage:.1f}%</div>', 
                           unsafe_allow_html=True)
                
                st.progress(min(percentage / 100, 1.0))
                
                
                col1, col2 = st.columns(2)
                col1.metric("Current Intake", f"{current_intake:.1f}L")
                col2.metric("Activity Level", activity)
    
    
    with tab2:
        st.subheader("User Profile Setup")
        
        profile = st.session_state.get('user_profile')
        if not profile:
            st.warning("Select a user ID in sidebar")
        else:
            base_info = profile.data.get('base_info', {})
            
            col1, col2 = st.columns(2)
            with col1:
                age = st.number_input("Age", min_value=10, max_value=100, 
                                    value=base_info.get('age', 25))
                weight = st.number_input("Weight (kg)", min_value=30, max_value=200, 
                                       value=base_info.get('weight', 70))
            
            with col2:
                gender = st.selectbox("Gender", ["Male", "Female"], 
                                    index=0 if base_info.get('gender') == 'Male' else 1)
                location = st.text_input("Location (City)", 
                                       value=profile.data.get('location', 'New York'))
            
            if st.button(" Save Profile", use_container_width=True, type="primary"):
                profile.set_base_info(age, gender, weight, location)
                st.success(" Profile saved!")
                st.rerun()
            
            
            if base_info.get('weight'):
                st.markdown("---")
                st.subheader("Current Profile")
                st.write(f"**Age:** {base_info.get('age')} years")
                st.write(f"**Gender:** {base_info.get('gender')}")
                st.write(f"**Weight:** {base_info.get('weight')} kg")
                st.write(f"**Location:** {profile.data.get('location', 'Not set')}")
                st.write(f"**Daily Water Goal:** {base_info.get('recommended_daily_intake', 0):.2f}L")
    
    
    with tab3:
        st.subheader("7-Day Sweat Calibration")
        
        profile = st.session_state.get('user_profile')
        if not profile:
            st.warning("Select a user ID in sidebar")
        else:
            cal_data = get_sweat_calibration_data(profile)
            
            if cal_data['is_calibrated']:
                st.success(f" Calibration Complete!")
                st.metric("Average Sweat (Moderate Baseline)", cal_data['average_sweat'])
                st.info("**Activity Levels:**\n- Below average = Low activity\n- At average = Moderate activity\n- Above average = High activity")
                
                if st.button(" Reset Calibration", use_container_width=True):
                    profile.data['sweat_calibration'] = {
                        'is_calibrated': False,
                        'daily_readings': [],
                        'average_sweat': None
                    }
                    profile.save()
                    st.rerun()
            else:
                st.write("Enter 7 days of sweat readings to calculate your baseline.")
            
            st.markdown("---")
            st.subheader("Enter 7 Days of Readings")
            readings = []
            col1, col2 = st.columns(2)
            
            with col1:
                readings.append(st.number_input("Day 1", min_value=0.0, max_value=100.0, value=25.0, step=0.1, key="day1"))
                readings.append(st.number_input("Day 2", min_value=0.0, max_value=100.0, value=25.0, step=0.1, key="day2"))
                readings.append(st.number_input("Day 3", min_value=0.0, max_value=100.0, value=25.0, step=0.1, key="day3"))
                readings.append(st.number_input("Day 4", min_value=0.0, max_value=100.0, value=25.0, step=0.1, key="day4"))
            
            with col2:
                readings.append(st.number_input("Day 5", min_value=0.0, max_value=100.0, value=25.0, step=0.1, key="day5"))
                readings.append(st.number_input("Day 6", min_value=0.0, max_value=100.0, value=25.0, step=0.1, key="day6"))
                readings.append(st.number_input("Day 7", min_value=0.0, max_value=100.0, value=25.0, step=0.1, key="day7"))
            
            
            average = sum(readings) / 7
            st.info(f" Average: {average:.2f}")
            
            if st.button(" Set Calibration", use_container_width=True, type="primary"):
                
                profile.data['sweat_calibration'] = {
                    'is_calibrated': True,
                    'daily_readings': [
                        {'date': f'Day {i+1}', 'sweat_value': readings[i]} 
                        for i in range(7)
                    ],
                    'average_sweat': round(average, 2)
                }
                profile.save()
                st.balloons()
                st.success(f"🎉 Calibration complete! Average: {average:.2f}")
                st.rerun()


if __name__ == "__main__":
    main()
