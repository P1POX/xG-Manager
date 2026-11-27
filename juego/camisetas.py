"""Colores y patrón de la camiseta local de cada club (aproximados, temporada 2023-24).

Cada entrada: nombre del club en el dataset -> (color principal, color secundario, patrón).
Patrones: "liso", "rayas" (verticales), "aros" (horizontales) y "mitades".
Los clubes que no estén aquí usan un color generado a partir del nombre (ver datos.colores_club).
"""

KITS = {
    # Premier League
    "Manchester City": ("6CABDD", "FFFFFF", "liso"),
    "Liverpool": ("C8102E", "FFFFFF", "liso"),
    "Arsenal": ("EF0107", "FFFFFF", "liso"),
    "Manchester United": ("DA291C", "FFFFFF", "liso"),
    "Newcastle United": ("111111", "FFFFFF", "rayas"),
    "Tottenham Hotspur": ("FFFFFF", "132257", "liso"),
    "Aston Villa": ("670E36", "95BFE5", "liso"),
    "Chelsea": ("034694", "FFFFFF", "liso"),
    "West Ham United": ("7A263A", "1BB1E7", "liso"),
    "Everton": ("003399", "FFFFFF", "liso"),
    "Nottingham Forest": ("DD0000", "FFFFFF", "liso"),
    "Fulham": ("FFFFFF", "111111", "liso"),
    "Brighton & Hove Albion": ("0057B8", "FFFFFF", "rayas"),
    "Wolverhampton Wanderers": ("FDB913", "231F20", "liso"),
    "Crystal Palace": ("1B458F", "C4122E", "rayas"),
    "Brentford": ("E30613", "FFFFFF", "rayas"),
    "AFC Bournemouth": ("DA291C", "111111", "rayas"),
    "Burnley": ("6C1D45", "99D6EA", "liso"),
    "Sheffield United": ("EE2737", "FFFFFF", "rayas"),
    "Luton Town": ("F78F1E", "002D62", "liso"),
    # La Liga
    "Real Madrid": ("FFFFFF", "00529F", "liso"),
    "FC Barcelona": ("A50044", "004D98", "rayas"),
    "Atlético Madrid": ("CB3524", "FFFFFF", "rayas"),
    "Sevilla": ("FFFFFF", "D71920", "liso"),
    "Athletic Club": ("EE2523", "FFFFFF", "rayas"),
    "Real Betis": ("0BB363", "FFFFFF", "rayas"),
    "Real Sociedad": ("0067B1", "FFFFFF", "rayas"),
    "Villarreal": ("FBE122", "005187", "liso"),
    "Osasuna": ("D91A21", "0A346F", "liso"),
    "Celta de Vigo": ("8AC3EE", "FFFFFF", "liso"),
    "Mallorca": ("E20613", "111111", "liso"),
    "Rayo Vallecano": ("FFFFFF", "E20613", "liso"),
    "Getafe": ("005999", "FFFFFF", "liso"),
    "Girona": ("CD2534", "FFFFFF", "rayas"),
    "Valencia": ("FFFFFF", "111111", "liso"),
    "Almería": ("EE1119", "FFFFFF", "rayas"),
    "Cádiz": ("FDE100", "0D3C8B", "liso"),
    "Las Palmas": ("FFCD00", "0057B8", "liso"),
    "Granada": ("A61B29", "FFFFFF", "rayas"),
    "Deportivo Alavés": ("0761AF", "FFFFFF", "rayas"),
    # Bundesliga
    "FC Bayern München": ("DC052D", "FFFFFF", "liso"),
    "Borussia Dortmund": ("FDE100", "111111", "liso"),
    "Bayer 04 Leverkusen": ("E32221", "111111", "liso"),
    "RB Leipzig": ("FFFFFF", "DD0741", "liso"),
    "VfL Wolfsburg": ("65B32E", "FFFFFF", "liso"),
    "FC Union Berlin": ("EB1923", "FFFFFF", "liso"),
    "Borussia Mönchengladbach": ("FFFFFF", "00A650", "liso"),
    "SC Freiburg": ("E2001A", "FFFFFF", "liso"),
    "Eintracht Frankfurt": ("111111", "E1000F", "liso"),
    "TSG Hoffenheim": ("1961B5", "FFFFFF", "liso"),
    "FSV Mainz 05": ("C3141E", "FFFFFF", "liso"),
    "FC Köln": ("FFFFFF", "ED1C24", "liso"),
    "Werder Bremen": ("1D9053", "FFFFFF", "liso"),
    "FC Augsburg": ("BA3733", "006A3A", "rayas"),
    "VfB Stuttgart": ("FFFFFF", "E32219", "liso"),
    "VfL Bochum 1848": ("005CA9", "FFFFFF", "liso"),
    "Darmstadt 98": ("004B9B", "FFFFFF", "liso"),
    "Heidenheim": ("E2001A", "003C7B", "rayas"),
    # Serie A
    "Inter": ("0068B2", "0A0A14", "rayas"),
    "Napoli": ("12A0D7", "FFFFFF", "liso"),
    "Juventus": ("FFFFFF", "111111", "rayas"),
    "Lazio": ("87D8F7", "FFFFFF", "liso"),
    "Milan": ("FB090B", "111111", "rayas"),
    "Roma": ("8E1F2F", "F0BC42", "liso"),
    "Atalanta": ("1E71B8", "111111", "rayas"),
    "Fiorentina": ("482E92", "FFFFFF", "liso"),
    "Torino": ("8A1E41", "FFFFFF", "liso"),
    "Monza": ("D6001C", "FFFFFF", "liso"),
    "Sassuolo": ("00A651", "111111", "rayas"),
    "Udinese": ("FFFFFF", "111111", "rayas"),
    "Bologna": ("C8102E", "1A2F5A", "rayas"),
    "Hellas Verona": ("FFDD00", "003DA5", "liso"),
    "Empoli": ("0066B3", "FFFFFF", "liso"),
    "Salernitana": ("7B1E3A", "FFFFFF", "liso"),
    "Genoa": ("C8102E", "0B2A5B", "mitades"),
    "Lecce": ("F6D000", "D2001C", "rayas"),
    "Cagliari": ("B2122B", "0A2A5B", "rayas"),
    "Frosinone": ("F7D118", "1A4FA1", "liso"),
    # Ligue 1
    "Paris Saint Germain": ("0B2A5B", "E10600", "liso"),
    "Olympique de Marseille": ("FFFFFF", "2FAEE0", "liso"),
    "Lens": ("E30613", "F6C700", "rayas"),
    "Monaco": ("E30613", "FFFFFF", "mitades"),
    "Lille": ("E01E13", "FFFFFF", "liso"),
    "Olympique Lyonnais": ("FFFFFF", "1B3E8C", "liso"),
    "Nice": ("E30613", "111111", "rayas"),
    "Rennes": ("E2001A", "111111", "liso"),
    "Montpellier": ("003B8E", "F36C21", "liso"),
    "Nantes": ("FCD116", "00A650", "liso"),
    "Lorient": ("F58220", "111111", "liso"),
    "Stade de Reims": ("E30613", "FFFFFF", "liso"),
    "Strasbourg": ("0A5CA8", "FFFFFF", "liso"),
    "Brest": ("E30613", "FFFFFF", "liso"),
    "Clermont": ("C8102E", "0A3D7C", "rayas"),
    "Toulouse": ("5B2C83", "FFFFFF", "liso"),
    "Metz": ("7B1E3A", "FFFFFF", "liso"),
    "Le Havre": ("5BC1E8", "0B2A5B", "liso"),
}


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def kit(nombre):
    """(color1, color2, patrón) del club, o None si no está en la tabla."""
    k = KITS.get(nombre)
    return (_rgb(k[0]), _rgb(k[1]), k[2]) if k else None


_PORTEROS = [(46, 184, 92), (255, 145, 0), (28, 28, 34), (160, 90, 200), (240, 228, 60), (0, 176, 210), (230, 60, 150)]


def color_portero(c1, c2):
    """Camiseta de portero: el color más distinto a los dos del club (el portero nunca viste igual que el equipo)."""
    def dist(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5
    base = max(_PORTEROS, key=lambda c: min(dist(c, c1), dist(c, c2)))
    oscuro = (20, 20, 26) if sum(base) > 300 else (235, 235, 240)
    return base, oscuro
