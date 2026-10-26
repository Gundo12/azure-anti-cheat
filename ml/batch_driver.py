import glob
import os
from os.path import basename
from typing import List

import joblib
import pandas as pd


def init() -> None:
    global model
    model_directory = os.environ["AZUREML_MODEL_DIR"]
    model_files = glob.glob(f"{model_directory}/**/*.pkl", recursive=True)

    if not model_files:
        raise FileNotFoundError(
            f"Kein .pkl-Modell unter {model_directory} gefunden."
        )

    model = joblib.load(model_files[0])


def run(mini_batch: List[str]) -> pd.DataFrame:
    results: list[dict] = []

    for file_path in mini_batch:
        frame = pd.read_csv(file_path)
        predictions = model.predict(frame)

        for row_index, prediction in enumerate(predictions):
            results.append(
                {
                    "file": basename(file_path),
                    "row": row_index,
                    "prediction": prediction,
                }
            )

    return pd.DataFrame(results)
