# Installation und Konfiguration

## 1. Benötigte Komponenten

Für einen vollständigen Lauf werden benötigt:

- Python 3.10 oder neuer
- Azure Functions Core Tools für die lokale Function-Ausführung
- Azure Service Bus mit einer Queue
- Azure Storage Account mit Blob-Container
- Azure Machine Learning Workspace mit Compute, Modell und Batch Endpoint
- Azure Cosmos DB mit Datenbank und Container
- ein separater Blob-Container für die Ausgabe des ML-Jobs

## 2. Datengenerator einrichten

Im Projektverzeichnis eine virtuelle Umgebung erstellen:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Service-Bus-Verbindung als Umgebungsvariable setzen:

```powershell
$env:SERVICEBUS_CONNECTION_STRING = "<connection-string>"
```

Beispieldaten erzeugen und versenden:

```powershell
python generator.py `
  --queue-name "<queue-name>" `
  --matches 120 `
  --rounds-min 10 `
  --rounds-max 30 `
  --players 10 `
  --rate 6 `
  --duration 60
```

Der Generator legt standardmäßig `generated_matches.csv` an. Die Datei ist nur
ein lokales Testartefakt und wird durch `.gitignore` ausgeschlossen.

## 3. Function App lokal konfigurieren

Abhängigkeiten installieren:

```powershell
cd functionapp
pip install -r requirements.txt
```

Für die lokale Ausführung eine nicht versionierte Datei
`functionapp/local.settings.json` anlegen:

```json
{
  "IsEncrypted": false,
  "Values": {
    "AzureWebJobsStorage": "<functions-storage-connection>",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AZURE_SUBSCRIPTION_ID": "<subscription-id>",
    "AZURE_RESOURCE_GROUP": "<resource-group>",
    "AZURE_ML_WORKSPACE": "<workspace-name>",
    "SERVICEBUS_CONNECTION_STRING": "<connection-string>",
    "SERVICEBUS_QUEUE_NAME": "<queue-name>",
    "INPUT_BLOB_CONNECTION_STRING": "<connection-string>",
    "INPUT_BLOB_CONTAINER_NAME": "<container-name>",
    "COSMOS_CONNECTION_STRING": "<connection-string>",
    "COSMOS_DATABASE_NAME": "<database-name>",
    "COSMOS_CONTAINER_NAME": "<container-name>",
    "AML_OUTPUT_BLOB_CONNECTION_STRING": "<connection-string>",
    "AML_OUTPUT_BLOB_CONTAINER_NAME": "<container-name>",
    "AML_OUTPUT_FOLDER": "batch-jobs/predictions",
    "AML_OUTPUT_BLOB_PATH": "batch-jobs/predictions/predictions.csv",
    "AML_BATCH_ENDPOINT_NAME": "<endpoint-name>"
  }
}
```

Die lokale Authentifizierung am Azure ML Workspace erfolgt über
`DefaultAzureCredential`. Dafür kann beispielsweise vorher `az login`
ausgeführt werden.

Function Host starten:

```powershell
func start
```

## 4. ML Batch Endpoint

Das bereinigte
[`Notebook_endpoint.ipynb`](../ml/Notebook_endpoint.ipynb) bildet die
Einrichtung des ML-Teils ab. Es enthält die Schritte für:

1. Anmeldung und Verbindung mit dem Azure ML Workspace,
2. Erstellung des Batch Endpoints,
3. Registrierung des Modells,
4. Einrichtung des Compute-Clusters und der Laufzeitumgebung,
5. Erstellung des Deployments mit `batch_driver.py`,
6. Festlegung des Standard-Deployments,
7. Testaufruf und Kontrolle der Ausgabe.

Vor der Ausführung müssen im Notebook die Platzhalter
`YOUR_AZURE_SUBSCRIPTION_ID`, `YOUR_RESOURCE_GROUP` und
`YOUR_AZURE_ML_WORKSPACE` ersetzt werden. Zusätzlich werden ein trainiertes
`model.pkl`, eine zum Modell passende `conda.yaml` und eine Feature-Datei
`sample-data.csv` benötigt.

Das Notebook kann in Azure Machine Learning Studio oder in einer lokalen
Jupyter-Umgebung mit angemeldeter Azure CLI ausgeführt werden. Die Zellen
sollten von oben nach unten ausgeführt und die zurückgegebenen Ressourcennamen
anschließend in den App Settings der Function hinterlegt werden.

### 4.1 Bestandteile des Deployments

Der Batch Endpoint benötigt:

1. ein registriertes Klassifikationsmodell,
2. eine Python-Umgebung mit `pandas`, `joblib` und der Bibliothek des Modells,
3. einen CPU- oder GPU-Compute-Cluster,
4. `ml/batch_driver.py` als Scoring-Skript,
5. eine Batch Deployment Configuration mit `predictions.csv` als Ausgabe.

Das Scoring-Skript sucht das erste `.pkl`-Modell unter
`AZUREML_MODEL_DIR`, liest jede übergebene CSV-Datei und führt
`model.predict()` aus. Modell und Umgebung müssen daher gemeinsam versioniert
werden.

## 5. Bereitstellung in Azure

Alle Werte aus `local.settings.json` werden in der bereitgestellten Function App
als Application Settings konfiguriert. Die lokale Datei selbst darf nicht
veröffentlicht werden.

Anschließend kann die Function App mit den Azure Functions Core Tools
bereitgestellt werden:

```powershell
func azure functionapp publish <function-app-name>
```

Die verwaltete Identität der Function App benötigt Zugriff auf den Azure ML
Workspace. Für die übrigen Dienste verwendet der aktuelle Code Connection
Strings aus den App Settings.

## 6. Testablauf

1. Function App starten und Logs beobachten.
2. Mit dem Generator wenige Matches an die Queue senden.
3. Prüfen, ob die Queue beim nächsten Timerlauf geleert wird.
4. Kontrollieren, ob eine Feature-CSV im Eingabecontainer entsteht.
5. Status und Logs des Azure-ML-Batchjobs prüfen.
6. Ausgabe `predictions.csv` im ML-Datastore kontrollieren.
7. Ergebnisdokumente in Cosmos DB prüfen.

Für einen kleinen Funktionstest empfiehlt sich eine kurze Generatorlaufzeit:

```powershell
python generator.py --queue-name "<queue-name>" --matches 5 --players 4 --rate 1 --duration 5
```

## 7. Sicherheit

- Keine Connection Strings, Account Keys oder lokale Settings committen.
- Bereits veröffentlichte Schlüssel unmittelbar rotieren.
- Rechte nach dem Least-Privilege-Prinzip vergeben.
- Für den produktiven Betrieb Connection Strings schrittweise durch Managed
  Identities ersetzen.
- Zugriff auf Storage, Service Bus, Azure ML und Cosmos DB über private
  Netzwerke oder geeignete Firewallregeln begrenzen.
