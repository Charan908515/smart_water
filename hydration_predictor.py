import joblib
import numpy as np
import os

class HydrationPredictor:
    
    def __init__(self):
        self.model_path = 'models/hydration_model.pkl'
        self.encoders_path = 'models/label_encoders.pkl'
        self.features_path = 'models/feature_cols.pkl'
        
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                "Model not found! Please run 'python model_training.py' first."
            )
        
        self.model = joblib.load(self.model_path)
        self.label_encoders = joblib.load(self.encoders_path)
        self.feature_cols = joblib.load(self.features_path)
    
    def predict(self, age, gender, weight, activity_level, weather, water_intake):
        """
        Predict hydration risk level
        
        Args:
            age: int (18-70)
            gender: str ('Male' or 'Female')
            weight: int (kg)
            activity_level: str ('Low', 'Moderate', 'High')
            weather: str ('Cold', 'Normal', 'Hot')
            water_intake: float (liters)
        
        Returns:
            dict with prediction results
        """
        features = {
            'Age': age,
            'Gender': gender,
            'Weight (kg)': weight,
            'Daily Water Intake (liters)': water_intake,
            'Physical Activity Level': activity_level,
            'Weather': weather
        }
        
        for col in ['Gender', 'Physical Activity Level', 'Weather']:
            try:
                features[col] = self.label_encoders[col].transform([features[col]])[0]
            except ValueError:
                raise ValueError(f"Invalid value for {col}: {features[col]}")
        
        X = np.array([[
            features['Age'],
            features['Gender'],
            features['Weight (kg)'],
            features['Daily Water Intake (liters)'],
            features['Physical Activity Level'],
            features['Weather']
        ]])
        
        prediction = self.model.predict(X)[0]
        probabilities = self.model.predict_proba(X)[0]
        
        class_names = self.model.classes_
        prob_dict = {class_name: prob for class_name, prob in zip(class_names, probabilities)}
        
        confidence = max(probabilities)
        
        recommendations = {
            'Good': "Great! You're well hydrated. Keep it up!",
            'Poor': "Your hydration level is poor. Drink more water!"
        }
        
        statuses = {
            'Good': 'Optimal',
            'Poor': 'Dehydrated'
        }
        
        return {
            'risk_level': prediction,
            'hydration_status': statuses.get(prediction, 'Unknown'),
            'confidence': confidence,
            'probabilities': prob_dict,
            'recommendation': recommendations.get(prediction, "Stay hydrated!")
        }


def demo_predictor():
    """Demo the hydration predictor"""
    print("=" * 60)
    print("HYDRATION PREDICTOR DEMO")
    print("=" * 60)
    
    try:
        predictor = HydrationPredictor()
        
        test_cases = [
            {
                'name': 'Well Hydrated Person',
                'age': 25,
                'gender': 'Male',
                'weight': 70,
                'activity_level': 'Moderate',
                'weather': 'Normal',
                'water_intake': 2.5
            },
            {
                'name': 'Low Hydration',
                'age': 30,
                'gender': 'Female',
                'weight': 60,
                'activity_level': 'High',
                'weather': 'Hot',
                'water_intake': 1.5
            },
            {
                'name': 'Critical Dehydration',
                'age': 40,
                'gender': 'Male',
                'weight': 80,
                'activity_level': 'High',
                'weather': 'Hot',
                'water_intake': 1.0
            }
        ]
        
        for i, case in enumerate(test_cases, 1):
            print(f"\nTest Case {i}: {case['name']}")
            print("-" * 60)
            print(f"Age: {case['age']}, Gender: {case['gender']}, Weight: {case['weight']}kg")
            print(f"Activity: {case['activity_level']}, Weather: {case['weather']}")
            print(f"Water Intake: {case['water_intake']}L")
            
            result = predictor.predict(
                age=case['age'],
                gender=case['gender'],
                weight=case['weight'],
                activity_level=case['activity_level'],
                weather=case['weather'],
                water_intake=case['water_intake']
            )
            
            print(f"\nPrediction: {result['risk_level']}")
            print(f"Confidence: {result['confidence']:.1%}")
            print(f"Probabilities:")
            for risk, prob in result['probabilities'].items():
                print(f"  {risk}: {prob:.1%}")
            print(f"Recommendation: {result['recommendation']}")
        
        print("\n" + "=" * 60)
        
    except FileNotFoundError as e:
        print(f"\nError: {e}")
        print("Please run 'python model_training.py' first to train the model.")


if __name__ == "__main__":
    demo_predictor()
