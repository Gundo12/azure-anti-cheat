import datetime
import io
import json
import logging
import os
import tempfile
import uuid

import azure.functions as func
import pandas as pd
from azure.ai.ml import Input, MLClient, Output
from azure.ai.ml.constants import AssetTypes
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient
from azure.storage.blob import BlobServiceClient


def require_setting(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Die Einstellung {name} ist nicht konfiguriert.")
    return value


credential = DefaultAzureCredential()
ml_client = MLClient(
    credential,
    require_setting("AZURE_SUBSCRIPTION_ID"),
    require_setting("AZURE_RESOURCE_GROUP"),
    require_setting("AZURE_ML_WORKSPACE"),
)

input_blob_service = BlobServiceClient.from_connection_string(
    require_setting("INPUT_BLOB_CONNECTION_STRING")
)
input_blob_container = input_blob_service.get_container_client(
    require_setting("INPUT_BLOB_CONTAINER_NAME")
)

cosmos_client = CosmosClient.from_connection_string(
    require_setting("COSMOS_CONNECTION_STRING")
)
cosmos_database = cosmos_client.get_database_client(
    require_setting("COSMOS_DATABASE_NAME")
)
cosmos_container = cosmos_database.get_container_client(
    require_setting("COSMOS_CONTAINER_NAME")
)

ml_output_blob_service = BlobServiceClient.from_connection_string(
    require_setting("AML_OUTPUT_BLOB_CONNECTION_STRING")
)
ml_output_container = ml_output_blob_service.get_container_client(
    require_setting("AML_OUTPUT_BLOB_CONTAINER_NAME")
)

service_bus_connection = require_setting("SERVICEBUS_CONNECTION_STRING")
service_bus_queue = require_setting("SERVICEBUS_QUEUE_NAME")
ml_endpoint_name = require_setting("AML_BATCH_ENDPOINT_NAME")
ml_output_folder = os.getenv("AML_OUTPUT_FOLDER", "batch-jobs/predictions")
ml_output_blob_path = os.getenv(
    "AML_OUTPUT_BLOB_PATH",
    f"{ml_output_folder}/predictions.csv",
)

default_datastore = ml_client.datastores.get_default()
app = func.FunctionApp()

model_features = [
    "round_number",
    "rounds_played",
    "shots_fired_round",
    "hits_round",
    "headshots_round",
    "accuracy_round",
    "headshot_accuracy_round",
    "kills_round",
    "deaths_round",
    "assists_round",
    "damage_this_round",
    "cum_kills",
    "cum_deaths",
    "cum_assists",
    "cum_damage",
]


@app.timer_trigger(
    schedule="10 */2 * * * *",
    arg_name="timer",
    run_on_startup=False,
    use_monitor=False,
)
def process_player_statistics(timer: func.TimerRequest) -> None:
    if timer.past_due:
        logging.warning("Timer-Ausführung ist verspätet.")

    matches = receive_matches()
    if not matches:
        logging.info("Keine Matchdaten zur Verarbeitung vorhanden.")
        return

    rounds = [round_data for match in matches for round_data in match]
    player_ids = [round_data.get("player_id") for round_data in rounds]
    input_frame = pd.DataFrame(rounds)[model_features]
    blob_client = upload_input_frame(input_frame)

    clear_previous_ml_output()
    invoke_ml_endpoint(blob_client.url)

    output_frame = read_predictions()
    predictions = output_frame.iloc[:, -1]
    input_frame["prediction"] = [int(value) for value in predictions.values]
    input_frame["player_id"] = player_ids
    save_to_cosmos(input_frame)

    logging.info("%s Datensätze gespeichert.", len(input_frame))


def receive_matches() -> list[list[dict]]:
    matches: list[list[dict]] = []

    with ServiceBusClient.from_connection_string(service_bus_connection) as client:
        receiver = client.get_queue_receiver(
            queue_name=service_bus_queue,
            prefetch_count=500,
        )
        with receiver:
            while True:
                messages = receiver.receive_messages(
                    max_message_count=200,
                    max_wait_time=5,
                )
                if not messages:
                    break

                for message in messages:
                    body = json.loads(b"".join(message.body).decode("utf-8"))
                    if isinstance(body, list):
                        matches.append(body)
                    else:
                        logging.warning("Nachricht mit unerwartetem Format verworfen.")
                    receiver.complete_message(message)

    return matches


def upload_input_frame(frame: pd.DataFrame):
    blob_name = (
        f"{datetime.datetime.now(datetime.UTC).strftime('%Y%m%dT%H%M%S')}-"
        f"{uuid.uuid4().hex}.csv"
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
        temp_path = temp_file.name

    try:
        frame.to_csv(temp_path, index=False)
        blob_client = input_blob_container.get_blob_client(blob_name)
        with open(temp_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        return blob_client
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def clear_previous_ml_output() -> None:
    for blob in ml_output_container.list_blobs(name_starts_with=ml_output_folder):
        ml_output_container.delete_blob(blob.name)


def invoke_ml_endpoint(input_url: str) -> None:
    output = Output(
        type=AssetTypes.URI_FILE,
        path=f"{default_datastore.id}/paths/{ml_output_folder}",
    )
    model_input = Input(type=AssetTypes.URI_FILE, path=input_url)
    job = ml_client.batch_endpoints.invoke(
        endpoint_name=ml_endpoint_name,
        input=model_input,
        outputs={"score": output},
    )
    ml_client.jobs.stream(job.name)


def read_predictions() -> pd.DataFrame:
    blob_client = ml_output_blob_service.get_blob_client(
        container=require_setting("AML_OUTPUT_BLOB_CONTAINER_NAME"),
        blob=ml_output_blob_path,
    )
    stream = blob_client.download_blob().readall()
    return pd.read_csv(io.BytesIO(stream), header=None)


def save_to_cosmos(frame: pd.DataFrame) -> None:
    for _, row in frame.iterrows():
        item = {
            key: value if pd.notna(value) else None
            for key, value in row.to_dict().items()
        }
        item["id"] = str(uuid.uuid4())
        cosmos_container.upsert_item(item)
