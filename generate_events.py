import json
from datetime import datetime, timezone

OUTPUT = "events.json"

def load_from_unico():
    """
    Qui in futuro potremo leggere output del bot vero.
    Per ora struttura pronta.
    """
    return {
        "corner": [],
        "value": [],
        "hot": []
    }

def main():
    sections = load_from_unico()

    data = {
        "updated_at": datetime.now(timezone.utc).strftime("%d/%m %H:%M"),
        "sections": sections
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("events.json aggiornato")

if __name__ == "__main__":
    main()
