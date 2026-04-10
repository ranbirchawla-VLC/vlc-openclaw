"""
fb_subs.py — Facebook character substitution table.
Import and call apply(text) to substitute all flagged terms.
Only used for Facebook Retail and Facebook Wholesale platforms.
"""

# Order matters — longer strings first to avoid partial matches
SUBSTITUTIONS = [
    # Brand names
    ("Patek Philippe", "Pat3k Phil!ppe"),
    ("Audemars Piguet", "Aud3mars P!guet"),
    ("Jaeger-LeCoultre", "Ja3ger-LeC0ultre"),
    ("TAG Heuer", "T@G Heuer"),
    ("Submariner", "Submar!ner"),
    ("Speedmaster", "Sp33dmaster"),
    ("Seamaster", "S3amaster"),
    ("Superocean", "Sup3rocean"),
    ("Aquanaut", "Aqu@naut"),
    ("Nautilus", "N@utilus"),
    ("Royal Oak", "R0yal 0ak"),
    ("Navitimer", "Nav!timer"),
    ("Datejust", "Dat3just"),
    ("Daytona", "Dayt0na"),
    ("Breitling", "Br3itling"),
    ("Panerai", "Pan3rai"),
    ("Hublot", "Hubl0t"),
    ("Cartier", "Cart!er"),
    ("Rolex", "R0lex"),
    ("Tudor", "Tud0r"),
    ("Omega", "Om3ga"),
    ("IWC", "!WC"),
    # Model terms
    ("Pilot's", "P!lot's"),
    ("Prince", "Pr!nce"),
    # Technical terms
    ("chronograph", "chr0nograph"),
    ("Chronograph", "Chr0nograph"),
    ("automatic", "@utomatic"),
    ("Automatic", "@utomatic"),
    ("calibre", "c@libre"),
    ("caliber", "c@liber"),
    ("Calibre", "C@libre"),
    ("Caliber", "C@liber"),
    ("warranty", "w@rranty"),
    ("Warranty", "W@rranty"),
    # Document terms
    ("Papers", "P@pers"),
    ("Valve", "V@lve"),
    # Payment terms
    ("Wire", "W!re"),
    ("Zelle", "Z3lle"),
    ("PayPal", "P@yPal"),
    ("fee", "f33"),
    ("Fee", "F33"),
]

FACEBOOK_PAYMENT_BLOCK = (
    "W!re or Z3lle preferred (under $5K). "
    "USDT (crypto) and CC (+4.5% f33) available.\n"
    "Ships fast from Colorado."
)


def apply(text: str) -> str:
    """Apply all Facebook character substitutions to text."""
    for clean, sub in SUBSTITUTIONS:
        text = text.replace(clean, sub)
    return text
