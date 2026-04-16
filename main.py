from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, computed_field
import joblib
import pandas as pd
import numpy as np
import smtplib
from dotenv import load_dotenv
import os
import logging
from logging.handlers import RotatingFileHandler
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Literal
from app.schemas import ForecastRequest, ForecastResponse

load_dotenv()
# ======================================================
# LOGGING CONFIGURATION
# ======================================================

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "itsm_api.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("ITSM-API")

# ======================================================
# SAFE MODEL LOADER
# ======================================================

def load_pipeline(path: str):
    try:
        logger.info(f"Loading model: {path}")
        model = joblib.load(path)
        logger.info(f"Model loaded successfully: {path}")
        return model
    except Exception as e:
        logger.critical(f"Model load failed: {path}", exc_info=True)
        raise RuntimeError(f"Model load failure: {path}")

pipeline_TC1 = load_pipeline("models/pipline_TC1.pkl")
pipeline_TC2 = load_pipeline("models/pipline_TC2.pkl")
pipeline_Dep = load_pipeline("models/pipline_Dep.pkl")
pipeline_rfc = load_pipeline("models/pipline_rfc.pkl")
model_overall_forecast= load_pipeline("models/model_overall_forecast.pkl")
model_CI_Cat_application= load_pipeline("models/model_CI_1.pkl")
model_CI_Cat_subapplication= load_pipeline("models/model_CI_2.pkl")
model_CI_Subcat_SBA=load_pipeline("models/model_CI_3.pkl")
model_CI_Subcat_WBA=load_pipeline("models/model_CI_4.pkl")

# ======================================================
# LOOKUP DICTIONARIES
# ======================================================

ci_fail_rate_dict={'Application Server': 0.0,'Automation Software': 0.05454545454545454,
 'Banking Device': 0.010285714285714285, 'Citrix': 0.049868766404199474,
 'Client Based Application': 0.016771488469601678, 'Controller': 0.0, 
 'DataCenterEquipment': 0.03292181069958848, 'Database': 0.01818181818181818,
 'Database Software': 0.0, 'Desktop': 0.002369668246445498,
 'Desktop Application': 0.036667565381504445, 'ESX Cluster': 0.0, 'ESX Server': 0.5,
 'Encryption': 0.044444444444444446, 'Exchange': 0.0, 'Firewall': 0.0, 'IPtelephony': 0.0, 
 'Instance': 0.0, 'Iptelephony': 0.0, 'KVM Switches': 0.0, 'Keyboard': 0.0, 'Laptop': 0.006842105263157895, 
 'Lines': 0.06666666666666667, 'Linux Server': 0.02040816326530612, 'MQ Queue Manager': 0.0, 
 'MigratieDummy': 0.034482758620689655, 'Modem': 0.3333333333333333, 'Monitor': 0.0, 'Neoview Server': 0.0, 
 'Net Device': 0.0, 'Network Component': 0.037037037037037035, 'NonStop Harddisk': 0.0, 
 'NonStop Server': 0.09090909090909091, 'Number': 0.0, 'Omgeving': 0.11904761904761904, 'Oracle Server': 0.0, 
 'Printer': 0.011494252873563218, 'Protocol': 0.0, 'RAC Service': 0.0, 'Router': 0.25, 'SAN': 0.013232514177693762, 
 'SAP': 0.002510460251046025, 'Scanner': 0.0, 'Security Software': 0.0, 'Server Based Application': 0.027790006603565925, 
 'SharePoint Farm': 0.0, 'Standard Application': 0.06493506493506493, 'Switch': 0.19230769230769232, 'System Software': 0.017167381974248927, 
 'Tape Library': 0.0, 'Thin Client': 0.0, 'UPS': 1.0, 'Unix Server': 0.0, 'VDI': 0.1111111111111111, 
 'Virtual Tape Server': 0.0, 'Web Based Application': 0.02530978117585025, 'Windows Server': 0.04964539007092199, 
 'Windows Server in extern beheer': 0.0, 'X86 Server': 0.0, 'zOS Cluster': 0.0, 'zOS Server': 0.0, 'zOS Systeem': 0.0}


ci_cat_fail_rate_dict={'Phone': 0.0, 'application': 0.029952476238119058, 
                       'applicationcomponent': 0.0, 'computer': 0.012415349887133182, 
                       'database': 0.017857142857142856, 'displaydevice': 0.0, 
                       'hardware': 0.03201970443349754, 'networkcomponents': 0.12121212121212122, 
                       'officeelectronics': 0.007194244604316547, 'software': 0.023809523809523808, 
                       'storage': 0.010719754977029096, 'subapplication': 0.015673575129533678}


department_code_map = {
    "Mainframe / Legacy": 13,
    "Server & OS Support": 7,
    "Network & Connectivity": 10,
    "Security": 12,
    "Database Support": 8,
    "Storage & Backup": 4,
    "Data Center Operations": 6,
    "Virtualization": 3,
    "Messaging & Collaboration": 9,
    "Application Support": 0,
    "Telephony": 2,
    "Automation / Tools": 11,
    "End User Computing": 1,
    "Unknown": 5
}


department_email_map = {
    "Mainframe / Legacy": "mainframe.support@company.com",
    "Server & OS Support": "itsmalert@gmail.com",
    "Network & Connectivity": "network.support@company.com",
    "Security": "security.ops@company.com",
    "Database Support": "database.support@company.com",
    "Storage & Backup": "storage.backup@company.com",
    "Data Center Operations": "datacenter.ops@company.com",
    "Virtualization": "virtualization@company.com",
    "Messaging & Collaboration": "messaging.collab@company.com",
    "Application Support": "itsmalert@gmail.com",
    "Telephony": "telephony.support@company.com",
    "Automation / Tools": "automation.tools@company.com",
    "End User Computing": "euc.support@company.com",
    "Unknown": "itsm.triage@company.com"
}

# ======================================================
# INPUT SCHEMA
# ======================================================

class InputData(BaseModel):
    CI_Cat: str = Field(..., example="application")
    CI_Subcat: str = Field(..., example="Application Server")
    Impact: int = Field(...,gt=0, lt=6, example="2")
    Urgency: int = Field(...,gt=0, lt=6, example="3")
    Category: str = Field(..., example="incident", description="only this options are allowed: ['incident', 'request for information', 'complaint', 'request for change']")
    No_of_Reassignments: int = Field( gte=0, example="1", description='Number of times the incident has been reassigned')
    No_of_Related_Incidents: int = Field( gte=0, example="0", description='Number of related incidents occurring in past.')
    No_of_Related_Interactions: int = Field(gte=0, example="2", description='Number of related interactions occur regarding this incidence with support team.')
    No_of_Related_Changes: int = Field(
    gte=0, example=0,
    description="Number of related RFCs/changes in past")
    Ticket_Short_Description: Optional[str] = Field(None, example="Explain the issue in 500 words", description="Brief description of the ticket", max_length=500)

    @computed_field
    @property
    def CI_Subcat_risk(self) -> float:
        return ci_fail_rate_dict.get(self.CI_Subcat, 0.0)

    @computed_field
    @property
    def CI_Cat_risk(self) -> float:
        return ci_cat_fail_rate_dict.get(self.CI_Cat.lower(), 0.0)

    @field_validator("Category")
    @classmethod
    def validate_category(cls, v):
        allowed = {
            "incident",
            "request for information",
            "complaint",
            "request for change"
        }
        v = v.lower()
        if v not in allowed:
            raise ValueError(f"Category must be one of {allowed}")
        return v

# ======================================================
# FASTAPI APP
# ======================================================

app = FastAPI(
    title="Incident Priority Prediction API",
    description="ITSM FastAPI with Logging",
    version="1.0.0"
)

@app.on_event("startup")
def startup_event():
    logger.info("🚀 ITSM FastAPI service started")

# ======================================================
# GLOBAL ERROR HANDLER
# ======================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception | Path: {request.url.path}",
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# ======================================================
# HOME
# ======================================================

@app.get("/")
def home():
    return {"message": "Welcome to ITSM API"}

# ======================================================
# PRIORITY ONLY
# ======================================================

@app.post("/predict_Level_of_priority")
def predict_priority(data: InputData):
    logger.info("Priority prediction request received")

    try:
        df = pd.DataFrame([{
            "CI_Cat": data.CI_Cat,
            "CI_Subcat": data.CI_Subcat,
            "Impact": data.Impact,
            "Urgency": data.Urgency,
            "Category": data.Category
        }])
        prediction = int(pipeline_TC1.predict(df)[0])
        logger.info(f"Priority predicted: {prediction}")

        return {
            "Level_of_priority": "High Priority" if prediction == 1 else "Low Priority",
            "prediction_code": prediction
        }

    except Exception:
        logger.error("Priority prediction failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Prediction failed")

# ======================================================
# EMAIL HELPERS
# ======================================================

def generate_short_alert_message(data, department, priority):
    return f"""
🚨 ITSM ALERT: {priority}

CI Category: {data.CI_Cat}
CI Subcategory: {data.CI_Subcat}
Category: {data.Category}
Impact: {data.Impact}
Urgency: {data.Urgency}
short Description: {data.Ticket_Short_Description or 'N/A'}

Assigned Team: {department}
"""

def send_email_alert(to_email, subject, message):
    if not to_email:
        logger.warning("Email skipped: recipient missing")
        return

    sender = os.getenv("ITSM_EMAIL")
    password = os.getenv("ITSM_EMAIL_PASSWORD")

    if not sender or not password:
        logger.warning("Email credentials missing")
        return

    try:
        logger.info(f"Sending email to {to_email}")

        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)

        logger.info("Email sent successfully")

    except Exception:
        logger.error("Email sending failed", exc_info=True)

# ======================================================
# PRIORITY + DEPARTMENT
# ======================================================

@app.post("/ticket_priority_and_department")
def predict_priority_and_department(data: InputData):
    logger.info("Ticket priority & department prediction started")

    try:
        priority_code = int(
            pipeline_TC2.predict(pd.DataFrame([{
                "CI_Cat": data.CI_Cat,
                "CI_Subcat": data.CI_Subcat,
                "Impact": data.Impact,
                "Urgency": data.Urgency,
                "Category": data.Category,
                "No_of_Reassignments": data.No_of_Reassignments
            }]))[0]
        )

        priority_label = "High Priority" if priority_code in [1, 2] else "Low Priority"

        dep_code = int(
            pipeline_Dep.predict(pd.DataFrame([{
                "CI_Cat": data.CI_Cat,
                "CI_Subcat": data.CI_Subcat
            }]))[0]
        )

        department = next(
            (k for k, v in department_code_map.items() if v == dep_code),
            "Unknown"
        )

        logger.info(f"Prediction completed | {priority_label} | {department}")

        if priority_code in [1, 2]:
            send_email_alert(
                department_email_map.get(department),
                "[HIGH PRIORITY] ITSM Ticket Alert",
                generate_short_alert_message(data, department, priority_label)
            )

        return {
            "Ticket_Priority": priority_label,
            "Department": department
        }

    except Exception:
        logger.error("Ticket processing failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Ticket processing failed")
    
# ======================================================
# RFC PREDICTION
# ======================================================

@app.post("/predict_rfc")
def predict_rfc(data: InputData):
    logger.info("RFC prediction request received")

    try:
        df = pd.DataFrame([{
            "CI_Subcat_risk": data.CI_Subcat_risk,
            "CI_Cat_risk": data.CI_Cat_risk,
            "Impact": data.Impact,
            "No_of_Related_Incidents": data.No_of_Related_Incidents,
            "No_of_Related_Changes": data.No_of_Related_Changes,
            "No_of_Related_Interactions": data.No_of_Related_Interactions
        }])

        prediction = int(pipeline_rfc.predict(df)[0])

        logger.info(f"RFC predicted: {prediction}")

        return {
            "Is_RFC": bool(prediction),
            "prediction_code": prediction
        }

    except Exception:
        logger.error("RFC prediction failed", exc_info=True)
        raise HTTPException(status_code=500, detail="RFC Prediction failed")


print("EMAIL:", os.getenv("ITSM_EMAIL"))
print("PWD LEN:", len(os.getenv("ITSM_EMAIL_PASSWORD", "")))

# ======================================================
# OVERALL FORECAST PREDICTION
# ======================================================
from joblib import load

MODEL_REGISTRY = {
    "Overall Incident Forecast": load("models/model_overall_forecast.pkl"),
    "Application Incidents": load("models/model_CI_1.pkl"),
    "Sub-Application Incidents": load("models/model_CI_2.pkl"),
    "Server Based Application Incidents": load("models/model_CI_3.pkl"),
    "Web Based Application Incidents": load("models/model_CI_4.pkl"),
}


class ForecastRequest(BaseModel):
    model_name: Literal[
        "Overall Incident Forecast",
        "Application Incidents",
        "Sub-Application Incidents",
        "Server Based Application Incidents",
        "Web Based Application Incidents"
    ]
    steps: int = 12

@app.post("/forecast")
def forecast(req: ForecastRequest):
    if req.model_name not in MODEL_REGISTRY:
        raise HTTPException(status_code=400, detail="Invalid model name")

    model = MODEL_REGISTRY[req.model_name]

    # ARIMA-style forecast
    forecast_log = model.forecast(steps=req.steps)
    forecast = np.expm1(forecast_log)

    # Monthly index
    start_date = pd.Timestamp.today().to_period("M").to_timestamp("M")
    idx = pd.date_range(start=start_date, periods=req.steps, freq="M")
    forecast = pd.Series(forecast, index=idx)
    forecast_clean = (
    forecast
    .replace([np.inf, -np.inf], np.nan)
    .fillna(0)
    .clip(lower=0)
    .round(0)
    .astype(int)
)

    return {
    "monthly": forecast_clean.to_dict(),
    "quarterly": forecast_clean.resample("Q").sum().to_dict(),
    "annual": forecast_clean.resample("Y").sum().to_dict(),
}
