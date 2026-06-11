"""
FHIR R4 export for MindSafe evaluation results.

Maps each video evaluation to a spec-valid FHIR R4 Bundle containing:
  - Patient            (synthetic de-identified child reference)
  - Observation × 6   (one per scoring dimension, LOINC-style coded)
  - Observation × 2   (dev_score and brainrot_index aggregate scores)
  - RiskAssessment     (brainrot risk level with outcome coding)
  - DocumentReference  (plain-text parent summary)

Usage:
    from evaluation.fhir_export import evaluation_to_fhir_bundle
    bundle = evaluation_to_fhir_bundle(results, child_age=4)
    json_str = bundle.model_dump_json(indent=2)

Honest framing: This tool performs pediatric behavioral-health media screening,
NOT clinical diagnosis. All resources carry an explicit disclaimer extension.
"""

import hashlib
import uuid
from datetime import UTC, datetime, timezone
from typing import Any, Dict, List, Optional

from fhir.resources.attachment import Attachment
from fhir.resources.bundle import Bundle, BundleEntry
from fhir.resources.codeableconcept import CodeableConcept
from fhir.resources.coding import Coding
from fhir.resources.documentreference import DocumentReference, DocumentReferenceContent
from fhir.resources.extension import Extension
from fhir.resources.meta import Meta
from fhir.resources.narrative import Narrative
from fhir.resources.observation import Observation
from fhir.resources.patient import Patient
from fhir.resources.quantity import Quantity
from fhir.resources.reference import Reference
from fhir.resources.riskassessment import RiskAssessment, RiskAssessmentPrediction

# ---------- Coding constants ----------
# Primary codes use real LOINC where a close match exists; a secondary
# MindSafe-specific code is carried as an additional coding slice for
# systems that need a 1:1 mapping to our scoring dimensions.
#
# LOINC mappings rationale:
#   72133-2  Child Behavior Checklist                 → pacing (behavioral stimulus load)
#   72107-6  Pediatric Symptom Checklist              → story (narrative/attention coherence)
#   54608-7  Language development finding             → language complexity
#   55757-9  Patient Health Questionnaire items       → SEL (social-emotional)
#   72106-8  Pediatric Quality of Life Inventory      → fantasy balance
#   72171-2  Functional Communication Measure         → interactivity
#   72169-6  Child development finding                → developmental aggregate
#   55110-1  Conclusions Document                     → overstimulation risk index

LOINC_SYSTEM   = "http://loinc.org"
MINDSAFE_SYSTEM = "https://mindsafe.app/fhir/CodeSystem/media-scoring"

DIMENSION_CODES = {
    #           (LOINC code,  LOINC display,                       MS code,  MS display)
    "pacing":        ("72133-2", "Child Behavior Checklist",                  "MS-001", "Media Pacing Score"),
    "story":         ("72107-6", "Pediatric Symptom Checklist",               "MS-002", "Narrative Coherence Score"),
    "language":      ("54608-7", "Language development finding",              "MS-003", "Language Complexity Score"),
    "sel":           ("55757-9", "Patient Health Questionnaire items",        "MS-004", "Social-Emotional Learning Score"),
    "fantasy":       ("72106-8", "Pediatric Quality of Life Inventory",       "MS-005", "Fantasy Balance Score"),
    "interactivity": ("72171-2", "Functional Communication Measure",          "MS-006", "Interactivity Score"),
}

AGGREGATE_CODES = {
    #                (LOINC code,  LOINC display,                  MS code,  MS display)
    "development_score": ("72169-6", "Child development finding",         "MS-010", "Developmental Appropriateness Score"),
    "brainrot_index":    ("55110-1", "Conclusions Document",              "MS-011", "Media Overstimulation Risk Index"),
}

# Risk outcome codes — no direct LOINC; use SNOMED CT for severity qualifiers
SNOMED_SYSTEM = "http://snomed.info/sct"
RISK_OUTCOME_CODES = {
    #              (SNOMED code, SNOMED display,                        MS code,  MS display)
    "Very Low Risk":  ("281300000", "Finding of very low risk",          "MS-R01", "Very low media overstimulation risk"),
    "Low Risk":       ("281301001", "Finding of low risk",               "MS-R02", "Low media overstimulation risk"),
    "Moderate Risk":  ("281302008", "Finding of moderate risk",          "MS-R03", "Moderate media overstimulation risk"),
    "High Risk":      ("281303003", "Finding of high risk",              "MS-R04", "High media overstimulation risk"),
    "Very High Risk": ("281304009", "Finding of very high risk",         "MS-R05", "Very high media overstimulation risk"),
}

DISCLAIMER_SYSTEM = "https://mindsafe.app/fhir/extension/disclaimer"
DISCLAIMER_VALUE  = (
    "This is a research-grade pediatric behavioral-health screening tool, "
    "NOT a medical device. Results are for parental guidance only and do not "
    "constitute clinical diagnosis or treatment recommendations."
)


# ---------- Helpers ----------

def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _synthetic_patient_id(child_age: float) -> str:
    """
    Generate a de-identified synthetic patient ID.
    Only age band is preserved; no name, DOB, or direct identifier.
    """
    age_band = f"age_{int(child_age)}"
    return "Patient/" + hashlib.sha256(age_band.encode()).hexdigest()[:16]


def _disclaimer_extension() -> Extension:
    return Extension(
        url=DISCLAIMER_SYSTEM,
        valueString=DISCLAIMER_VALUE,
    )


def _coding(system: str, code: str, display: str) -> Coding:
    return Coding(system=system, code=code, display=display)


def _codeable(code: str, display: str, system: str = MINDSAFE_SYSTEM) -> CodeableConcept:
    return CodeableConcept(
        coding=[_coding(system, code, display)],
        text=display,
    )


def _dual_codeable(
    loinc_code: str, loinc_display: str,
    ms_code: str, ms_display: str,
) -> CodeableConcept:
    """Two-slice coding: LOINC primary + MindSafe secondary."""
    return CodeableConcept(
        coding=[
            _coding(LOINC_SYSTEM, loinc_code, loinc_display),
            _coding(MINDSAFE_SYSTEM, ms_code, ms_display),
        ],
        text=ms_display,
    )


def _observation_base(
    obs_id: str,
    patient_ref: str,
    code: CodeableConcept,
    score_0_100: float,
    interpretation_text: str,
    subject_display: str,
    video_url: str | None = None,
) -> Observation:
    data: dict[str, Any] = {
        "id": obs_id,
        "status": "final",
        "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/Observation"]},
        "extension": [{"url": DISCLAIMER_SYSTEM, "valueString": DISCLAIMER_VALUE}],
        "code": code.model_dump(),
        "subject": {"reference": patient_ref, "display": subject_display},
        "effectiveDateTime": _now_iso(),
        "valueQuantity": {
            "value": round(score_0_100, 2),
            "unit": "score",
            "system": "http://unitsofmeasure.org",
            "code": "{score}",
        },
        "interpretation": [
            {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                    "code": "N",
                    "display": interpretation_text,
                }],
                "text": interpretation_text,
            }
        ],
    }
    if video_url:
        data["note"] = [{"text": f"Source video: {video_url}"}]
    return Observation(**data)


# ---------- Main export ----------

def evaluation_to_fhir_bundle(
    results: dict[str, Any],
    child_age: float,
    video_url: str | None = None,
) -> Bundle:
    """
    Convert a MindSafe evaluate_video() result dict into a FHIR R4 Bundle.

    Args:
        results:   output of evaluate_video() from evaluate_video.py
        child_age: child age in years (used to derive age band only)
        video_url: optional source YouTube URL (stored in Observation notes)

    Returns:
        A validated fhir.resources Bundle object.
    """
    bundle_id = str(uuid.uuid4())
    patient_id = _synthetic_patient_id(child_age)
    age_band = results.get("metadata", {}).get("age_band", "unknown")
    subject_display = f"Child (age band: {age_band})"

    overall = results.get("overall_scores", {})
    dim_scores = results.get("dimension_scores", {})
    interpretations = results.get("interpretations", {})
    parent_summary = results.get("parent_summary", "")

    entries: list[BundleEntry] = []
    _disclaimer_ext = {"url": DISCLAIMER_SYSTEM, "valueString": DISCLAIMER_VALUE}

    # --- Patient (synthetic, de-identified) ---
    patient_raw_id = patient_id.replace("Patient/", "")
    patient = Patient(**{
        "id": patient_raw_id,
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/Patient"],
            "tag": [{"system": "http://terminology.hl7.org/CodeSystem/v3-Confidentiality",
                     "code": "R", "display": "Restricted — research use only"}],
        },
        "extension": [_disclaimer_ext],
        "text": {
            "status": "generated",
            "div": f'<div xmlns="http://www.w3.org/1999/xhtml">Synthetic child reference, age band {age_band}. No PII stored.</div>',
        },
    })
    entries.append(BundleEntry(
        fullUrl=f"urn:uuid:{patient_raw_id}",
        resource=patient,
    ))

    # --- Dimension Observations ---
    for dim_key, (loinc_code, loinc_display, ms_code, ms_display) in DIMENSION_CODES.items():
        score = dim_scores.get(dim_key)
        if score is None:
            continue
        obs_id = f"obs-dim-{dim_key}-{bundle_id[:8]}"
        obs = _observation_base(
            obs_id=obs_id,
            patient_ref=patient_id,
            code=_dual_codeable(loinc_code, loinc_display, ms_code, ms_display),
            score_0_100=score,
            interpretation_text=_score_interpretation(score),
            subject_display=subject_display,
            video_url=video_url,
        )
        entries.append(BundleEntry(
            fullUrl=f"urn:uuid:{obs_id}",
            resource=obs,
        ))

    # --- Aggregate Score Observations ---
    for agg_key, (loinc_code, loinc_display, ms_code, ms_display) in AGGREGATE_CODES.items():
        score = overall.get(agg_key)
        if score is None:
            continue
        obs_id = f"obs-agg-{agg_key.replace('_', '-')}-{bundle_id[:8]}"
        obs = _observation_base(
            obs_id=obs_id,
            patient_ref=patient_id,
            code=_dual_codeable(loinc_code, loinc_display, ms_code, ms_display),
            score_0_100=score,
            interpretation_text=interpretations.get("developmental", "") if agg_key == "development_score"
                                 else interpretations.get("brainrot", ""),
            subject_display=subject_display,
            video_url=video_url,
        )
        entries.append(BundleEntry(
            fullUrl=f"urn:uuid:{obs_id}",
            resource=obs,
        ))

    # --- RiskAssessment (brainrot risk) ---
    brainrot_score = overall.get("brainrot_index", 0.0)
    brainrot_interp = interpretations.get("brainrot", "Unknown Risk")
    # Extract the first two words as risk label (e.g. "Very Low Risk")
    risk_label = _extract_risk_label(brainrot_interp)
    default_risk = ("281302008", "Finding of moderate risk", "MS-R03", "Moderate media overstimulation risk")
    snomed_code, snomed_display, ms_risk_code, ms_risk_display = RISK_OUTCOME_CODES.get(risk_label, default_risk)
    risk_outcome_cc = CodeableConcept(
        coding=[
            _coding(SNOMED_SYSTEM, snomed_code, snomed_display),
            _coding(MINDSAFE_SYSTEM, ms_risk_code, ms_risk_display),
        ],
        text=ms_risk_display,
    )

    ra_id = f"ra-{bundle_id[:8]}"
    ra = RiskAssessment(**{
        "id": ra_id,
        "status": "final",
        "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/RiskAssessment"]},
        "extension": [_disclaimer_ext],
        "subject": {"reference": patient_id, "display": subject_display},
        "occurrenceDateTime": _now_iso(),
        "method": _codeable("MS-METHOD-01", "MindSafe Behavioral Media Screening").model_dump(),
        "prediction": [{
            "outcome": risk_outcome_cc.model_dump(),
            "probabilityDecimal": round(brainrot_score / 100.0, 4),
            "rationale": brainrot_interp,
        }],
        "note": [{"text": interpretations.get("overall", "")}],
    })
    entries.append(BundleEntry(
        fullUrl=f"urn:uuid:{ra_id}",
        resource=ra,
    ))

    # --- DocumentReference (parent summary) ---
    if parent_summary:
        dr_id = f"dr-{bundle_id[:8]}"
        dr = DocumentReference(**{
            "id": dr_id,
            "status": "current",
            "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/DocumentReference"]},
            "extension": [_disclaimer_ext],
            "type": _codeable("34109-9", "Note", system="http://loinc.org").model_dump(),
            "subject": {"reference": patient_id, "display": subject_display},
            "date": _now_iso(),
            "description": "MindSafe parent summary",
            "content": [{
                "attachment": {
                    "contentType": "text/plain",
                    "data": _b64(parent_summary),
                    "title": "Parent Summary",
                }
            }],
        })
        entries.append(BundleEntry(
            fullUrl=f"urn:uuid:{dr_id}",
            resource=dr,
        ))

    # --- Bundle ---
    bundle = Bundle(**{
        "id": bundle_id,
        "type": "collection",
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/Bundle"],
            "tag": [{"system": DISCLAIMER_SYSTEM, "code": "research", "display": "Research use only"}],
        },
        "timestamp": _now_iso(),
        "entry": [e.model_dump(exclude_none=True) for e in entries],
    })

    return bundle


# ---------- Utilities ----------

def _score_interpretation(score: float) -> str:
    if score >= 75:
        return "H"  # High (good)
    elif score >= 50:
        return "N"  # Normal
    else:
        return "L"  # Low (concerning)


def _extract_risk_label(interp: str) -> str:
    """Map brainrot interpretation string to RISK_OUTCOME_CODES key."""
    interp_lower = interp.lower()
    if "very low" in interp_lower:
        return "Very Low Risk"
    elif "very high" in interp_lower:
        return "Very High Risk"
    elif "low" in interp_lower:
        return "Low Risk"
    elif "high" in interp_lower:
        return "High Risk"
    elif "moderate" in interp_lower:
        return "Moderate Risk"
    return "Moderate Risk"


def _b64(text: str) -> str:
    import base64
    return base64.b64encode(text.encode()).decode()
