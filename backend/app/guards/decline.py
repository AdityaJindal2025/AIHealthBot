"""Fixed, reviewed decline responses (AP §6.4). Schema-valid, `claims: []`, no digits."""

from app.guards.rules import Category
from app.schemas.model_output import AssistantOutput

TARGET_DECLINE = (
    "I can't help with personal calorie or weight targets. A registered dietitian or your doctor can give "
    "advice that fits your health, history and goals. I'm happy to help with general questions about foods, "
    "nutrients or food safety."
)

MEDICAL_DECLINE = (
    "I can't give medical advice, such as whether a food is right for a health condition, how it interacts "
    "with a medication, or how much of a medicine or supplement to take. Your doctor or pharmacist can advise "
    "you based on your health and history. I'm happy to help with general questions about foods, nutrients "
    "or food safety."
)

DECLINE_TEXTS: dict[Category, str] = {
    "calorie_target": TARGET_DECLINE,
    "weight_target": TARGET_DECLINE,
    "medical_advice": MEDICAL_DECLINE,
}


def build_decline(category: Category) -> AssistantOutput:
    return AssistantOutput(answer=DECLINE_TEXTS[category], claims=[])
