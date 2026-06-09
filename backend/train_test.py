import requests

response = requests.post(
    "http://localhost:8000/api/v1/models/train-model",
    json={
        "connection_id": "f0ab1c5c-bb3d-4dbc-9e5e-732b4bc764de",
        "name": "Churn Prediction Test",
        "goal": "classification",
        "target_column": "deal_stage",
        "source_table": "sales_pipeline",
        "hyperparameters": {}
    },
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer YOUR_TOKEN_HERE"
    }
)
print(response.status_code)
print(response.json())