import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import joblib
import os

def load_csv_data(csv_path='Daily_Water_Intake.csv'):
    """Load training data from CSV file"""
    print(f"   Loading data from: {csv_path}")
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    
    df = pd.read_csv(csv_path)
    
    print(f"   Loaded {len(df)} records")
    print(f"   Columns: {list(df.columns)}")
    
    # Remove any rows with missing values
    original_len = len(df)
    df = df.dropna()
    print(f"   After removing NaN: {len(df)} records (removed {original_len - len(df)})")
    
    return df


def train_model():
    """Train the hydration prediction model"""
    print("=" * 60)
    print("HYDRATION PREDICTION MODEL TRAINING")
    print("=" * 60)
    
    print("\n1. Loading training data from CSV...")
    df = load_csv_data('Daily_Water_Intake.csv')
    
    print(f"   Dataset shape: {df.shape}")
    print(f"   Class distribution:\n{df['Hydration Level'].value_counts()}")
    
    print("\n2. Preparing features...")
    # Use exact column names from CSV
    feature_cols = ['Age', 'Gender', 'Weight (kg)', 'Daily Water Intake (liters)', 'Physical Activity Level', 'Weather']
    X = df[feature_cols].copy()
    y = df['Hydration Level']
    
    label_encoders = {}
    for col in ['Gender', 'Physical Activity Level', 'Weather']:
        le = LabelEncoder()
        X[col] = le.fit_transform(X[col])
        label_encoders[col] = le
    
    print("\n3. Splitting data...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"   Training samples: {len(X_train)}")
    print(f"   Testing samples: {len(X_test)}")
    
    print("\n4. Training Random Forest model...")
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=42,
        class_weight='balanced'
    )
    model.fit(X_train, y_train)
    
    print("\n5. Evaluating model...")
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    
    print(f"\n   Accuracy: {accuracy:.2%}")
    print("\n   Classification Report:")
    print(classification_report(y_test, y_pred))
    
    print("\n   Confusion Matrix:")
    print(confusion_matrix(y_test, y_pred))
    
    print("\n   Feature Importance:")
    for feature, importance in zip(feature_cols, model.feature_importances_):
        print(f"   {feature}: {importance:.4f}")
    
    print("\n6. Saving model and encoders...")
    os.makedirs('models', exist_ok=True)
    
    joblib.dump(model, 'models/hydration_model.pkl')
    joblib.dump(label_encoders, 'models/label_encoders.pkl')
    joblib.dump(feature_cols, 'models/feature_cols.pkl')
    
    print("   Saved:")
    print("   - models/hydration_model.pkl")
    print("   - models/label_encoders.pkl")
    print("   - models/feature_cols.pkl")
    
    print("\n" + "=" * 60)
    print("TRAINING COMPLETE!")
    print("=" * 60)
    
    return model, label_encoders, feature_cols


if __name__ == "__main__":
    train_model()
