import discord # Potrzebne dla discord.Color
import os # Dodano dla zmiennych środowiskowych w sekcji API
import typing # Dodano dla type hinting w sekcji API

# --- Konfiguracja Systemu XP ---
XP_ZA_WIADOMOSC_MIN: int = 40
XP_ZA_WIADOMOSC_MAX: int = 50
COOLDOWN_XP_WIADOMOSC_SEKUNDY: int = 60
XP_ZA_GLOS_CO_ILE_MINUT: int = 5
XP_ZA_GLOS_ILOSC_MIN: int = 25
XP_ZA_GLOS_ILOSC_MAX: int = 35
XP_ZA_REAKCJE_MIN: int = 8
XP_ZA_REAKCJE_MAX: int = 12
COOLDOWN_XP_REAKCJE_SEKUNDY: int = 30
XP_BONUS_ZA_DZIEN_STREAKA: int = 30
MAX_DNI_STREAKA_DLA_BONUSU: int = 7
DUKATY_ZA_POZIOM: int = 150

CZYSZCZENIE_BONUSOW_CO_ILE_GODZIN: int = 24
SPRAWDZANIE_ROL_CZASOWYCH_CO_ILE_MINUT: int = 5

# --- KONFIGURACJA SYSTEMU MISJI ---
RESET_MISJI_DZIENNYCH_GODZINA_UTC: int = 4 # Godzina UTC, o której resetują się misje dzienne (np. 4 dla 4:00 AM UTC)
RESET_MISJI_TYGODNIOWYCH_DZIEN_TYGODNIA: int = 0 # Dzień tygodnia (0=Poniedziałek, 6=Niedziela), o którym resetują się misje tygodniowe
RESET_MISJI_TYGODNIOWYCH_GODZINA_UTC: int = 4 # Godzina UTC w dniu resetu misji tygodniowych


DEFINICJE_MISJI: dict = {
    "dzienna_aktywnosc_1": {
        "nazwa": "Poranny Zgiełk Kronik",
        "opis": "Napisz 15 wiadomości na dowolnych kanałach tekstowych.",
        "typ_misji": "dzienna",
        "warunki": [
            {"typ_warunku": "liczba_wiadomosci_od_resetu", "wartosc": 15}
        ],
        "nagrody": {"xp": 100, "gwiezdne_dukaty": 25},
        "ikona": "☀️"
    },
    "dzienna_reakcje_1": {
        "nazwa": "Echa Wspólnoty",
        "opis": "Dodaj 5 reakcji pod wiadomościami innych Kronikarzy.",
        "typ_misji": "dzienna",
        "warunki": [
            {"typ_warunku": "liczba_reakcji_od_resetu", "wartosc": 5}
        ],
        "nagrody": {"xp": 75, "gwiezdne_dukaty": 15},
        "ikona": "👍"
    },
    "dzienna_glos_1": {
        "nazwa": "Głosowe Narady",
        "opis": "Spędź co najmniej 10 minut na kanałach głosowych (nie AFK).",
        "typ_misji": "dzienna",
        "warunki": [
            {"typ_warunku": "czas_na_glosowym_od_resetu_sekundy", "wartosc": 600}
        ],
        "nagrody": {"xp": 120, "gwiezdne_dukaty": 30},
        "ikona": "🎙️"
    },
    "tygodniowa_aktywnosc_duza": {
        "nazwa": "Saga Tygodnia",
        "opis": "Napisz 100 wiadomości w ciągu tygodnia, wzbogacając Kroniki swoją opowieścią.",
        "typ_misji": "tygodniowa",
        "warunki": [
            {"typ_warunku": "liczba_wiadomosci_od_resetu", "wartosc": 100}
        ],
        "nagrody": {"xp": 500, "gwiezdne_dukaty": 150, "gwiezdne_krysztaly": 5},
        "ikona": "📜"
    },
    "tygodniowa_komenda_fun": {
        "nazwa": "Chwila Rozrywki",
        "opis": "Użyj komendy z kategorii 'Rozrywka' co najmniej 3 razy w tygodniu.",
        "typ_misji": "tygodniowa",
        "warunki": [
            {"typ_warunku": "uzycie_komendy_kategorii_od_resetu", "kategoria_komendy": "rozrywka", "wartosc": 3}
        ],
        "nagrody": {"xp": 100, "gwiezdne_dukaty": 50},
        "ikona": "🎲"
    },
    "jednorazowa_pierwsze_zaproszenie": {
        "nazwa": "Ambasador Kronik",
        "opis": "Zaproś Elarę na inny serwer, używając komendy /zapros.",
        "typ_misji": "jednorazowa",
        "warunki": [
            {"typ_warunku": "uzycie_komendy", "nazwa_komendy": "zapros", "wartosc": 1}
        ],
        "nagrody": {"xp": 200, "gwiezdne_dukaty": 100, "gwiezdne_krysztaly": 10},
        "ikona": "💌"
    },
    "jednorazowa_osiagniecie_poziom_5": {
        "nazwa": "Pierwsze Kroki Mocy",
        "opis": "Osiągnij 5. Poziom Mocy Opowieści.",
        "typ_misji": "jednorazowa",
        "warunki": [
            {"typ_warunku": "osiagniecie_poziomu_xp", "wartosc": 5}
        ],
        "nagrody": {"xp": 150, "gwiezdne_dukaty": 75},
        "ikona": "✨"
    },
    "dzienna_wygrany_konkurs": {
        "nazwa": "Szczęśliwy Zwycięzca Dnia",
        "opis": "Wygraj dzisiaj dowolny konkurs organizowany przez Elarę.",
        "typ_misji": "dzienna",
        "warunki": [
            {"typ_warunku": "wygraj_konkurs_od_resetu", "wartosc": 1}
        ],
        "nagrody": {"xp": 200, "gwiezdne_dukaty": 100, "gwiezdne_krysztaly": 2},
        "ikona": "🏆"
    },
    "tygodniowa_zakup_w_sklepie": {
        "nazwa": "Kolekcjoner Artefaktów",
        "opis": "Dokonaj zakupu przedmiotu 'Mały Zastrzyk Gwiezdnego Pyłu' w Skarbcu Artefaktów w tym tygodniu.",
        "typ_misji": "tygodniowa",
        "warunki": [
            {"typ_warunku": "uzyj_przedmiotu_ze_sklepu_od_resetu", "id_przedmiotu": "maly_boost_xp_1h", "wartosc": 1}
        ],
        "nagrody": {"xp": 150, "gwiezdne_dukaty": 75},
        "ikona": "🛍️"
    },
    "jednorazowa_dlugi_streak": {
        "nazwa": "Żelazna Konsekwencja",
        "opis": "Utrzymaj codzienną aktywność przez 7 dni z rzędu.",
        "typ_misji": "jednorazowa",
        "warunki": [
            {"typ_warunku": "osiagnij_x_streaka", "wartosc": 7}
        ],
        "nagrody": {"xp": 300, "gwiezdne_dukaty": 150, "gwiezdne_krysztaly": 10},
        "ikona": "🔗"
    }
}

# --- Konfiguracja Waluty Premium ---
NAZWA_WALUTY_PREMIUM: str = "Gwiezdne Kryształy"
SYMBOL_WALUTY_PREMIUM: str = "💠"
DOMYSLNY_KURS_WYMIANY_DUKATY_NA_KRYSZTALY: int = 1000

# --- Konfiguracja Systemu Osiągnięć ---
DEFINICJE_OSIAGNIEC: dict = {
    "aktywnosc_tekstowa": {
        "nazwa_bazowa": "Kronikarz Słowa",
        "opis_bazowy": "Zaangażowanie w dyskusje na całym serwerze.",
        "typ_warunku_bazowy": "liczba_wiadomosci",
        "ikona": "🖋️",
        "ukryte": False,
        "kategoria_osiagniecia": "Aktywność Ogólna",
        "tiery": [
            { "id": "wiadomosci_1", "nazwa_tieru": "Początkujący Skryba", "opis_tieru": "Napisz swoje pierwsze 10 wiadomości w Kronikach.", "wartosc_warunku": 10, "nagroda_xp": 25, "nagroda_dukaty": 20, "odznaka_emoji": "🗣️" },
            { "id": "wiadomosci_2", "nazwa_tieru": "Rozmowny Opowiadacz", "opis_tieru": "Podziel się 50 historiami (wiadomościami).", "wartosc_warunku": 50, "nagroda_xp": 75, "nagroda_dukaty": 40, "odznaka_emoji": "💬" },
            { "id": "wiadomosci_3", "nazwa_tieru": "Gawędziarz Kronik", "opis_tieru": "Twoje słowa niosą się echem - 100 wiadomości!", "wartosc_warunku": 100, "nagroda_xp": 150, "nagroda_dukaty": 75, "odznaka_emoji": "📜" },
            { "id": "wiadomosci_4", "nazwa_tieru": "Mistrz Elokwencji", "opis_tieru": "Prawdziwy weteran słowa pisanego - 500 wiadomości.", "wartosc_warunku": 500, "nagroda_xp": 500, "nagroda_dukaty": 250, "odznaka_emoji": "✒️" }
        ]
    },
    "aktywnosc_na_kanale_ogloszenia": {
        "nazwa_bazowa": "Głos Tawerny",
        "opis_bazowy": "Aktywność na kanale ogłoszeń.",
        "typ_warunku_bazowy": "liczba_wiadomosci_na_kanale",
        "id_kanalu_warunku": "ID_KANALU_OGLOSZEN", # WAŻNE: Podmień na rzeczywiste ID kanału!
        "ikona": "📢",
        "ukryte": False,
        "kategoria_osiagniecia": "Aktywność Specyficzna",
        "tiery": [
            { "id": "tawerna_wiad_10", "nazwa_tieru": "Bywalec Tawerny", "opis_tieru": "Zostaw 10 wiadomości w Tawernie Ogłoszeń.", "wartosc_warunku": 10, "nagroda_xp": 30, "nagroda_dukaty": 15, "odznaka_emoji": "🍻" },
            { "id": "tawerna_wiad_50", "nazwa_tieru": "Dusza Towarzystwa", "opis_tieru": "Twoje opowieści w Tawernie przyciągają tłumy - 50 wiadomości.", "wartosc_warunku": 50, "nagroda_xp": 100, "nagroda_dukaty": 50, "odznaka_emoji": "🎉" }
        ]
    },
    "poziom_doswiadczenia": {
        "nazwa_bazowa": "Wspinaczka po Szczeblach Mocy",
        "opis_bazowy": "Zdobywanie kolejnych poziomów doświadczenia.",
        "typ_warunku_bazowy": "poziom_xp",
        "ikona": "🌟",
        "ukryte": False,
        "kategoria_osiagniecia": "Postęp",
        "tiery": [
            { "id": "poziom_5", "nazwa_tieru": "Adept Kronik", "opis_tieru": "Osiągnij 5. Poziom Mocy Opowieści.", "wartosc_warunku": 5, "nagroda_xp": 50, "nagroda_dukaty": 30, "odznaka_emoji": "⭐" },
            { "id": "poziom_10", "nazwa_tieru": "Strażnik Wiedzy", "opis_tieru": "Osiągnij 10. Poziom Mocy Opowieści.", "wartosc_warunku": 10, "nagroda_xp": 120, "nagroda_dukaty": 60, "odznaka_emoji": "🌠" },
            { "id": "poziom_25", "nazwa_tieru": "Arcymistrz Opowieści", "opis_tieru": "Osiągnij 25. Poziom Mocy Opowieści.", "wartosc_warunku": 25, "nagroda_xp": 600, "nagroda_dukaty": 300, "odznaka_emoji": "💫" }
        ]
    },
    "bogactwo_dukatow": {
        "nazwa_bazowa": "Skarbiec Kronikarza",
        "opis_bazowy": "Gromadzenie Gwiezdnych Dukatów.",
        "typ_warunku_bazowy": "ilosc_dukatow",
        "ikona": "💰",
        "ukryte": False,
        "kategoria_osiagniecia": "Ekonomia",
        "tiery": [
            { "id": "dukaty_500", "nazwa_tieru": "Ziarnko do Ziarnka", "opis_tieru": "Zgromadź 500 Gwiezdnych Dukatów.", "wartosc_warunku": 500, "nagroda_xp": 50, "odznaka_emoji": "🪙" },
            { "id": "dukaty_2500", "nazwa_tieru": "Mieszek Pełen Blasku", "opis_tieru": "Twój skarbiec mieści 2500 Dukatów.", "wartosc_warunku": 2500, "nagroda_xp": 200, "odznaka_emoji": "💰" },
            { "id": "dukaty_10000", "nazwa_tieru": "Smoczy Skarb", "opis_tieru": "Posiadasz fortunę godną smoka - 10000 Dukatów!", "wartosc_warunku": 10000, "nagroda_xp": 1000, "odznaka_emoji": "🐉" }
        ]
    },
    "aktywnosc_reakcji": {
        "nazwa_bazowa": "Znawca Emocji",
        "opis_bazowy": "Reagowanie na wiadomości innych Kronikarzy.",
        "typ_warunku_bazowy": "liczba_reakcji",
        "ikona": "👍",
        "ukryte": False,
        "kategoria_osiagniecia": "Aktywność Społeczna",
        "tiery": [
            { "id": "reakcje_20", "nazwa_tieru": "Uważny Słuchacz", "opis_tieru": "Dodaj 20 reakcji pod wiadomościami.", "wartosc_warunku": 20, "nagroda_xp": 30, "nagroda_dukaty": 15, "odznaka_emoji": "👌" },
            { "id": "reakcje_100", "nazwa_tieru": "Empatyczny Komentator", "opis_tieru": "Twoje reakcje mówią więcej niż słowa - 100 reakcji!", "wartosc_warunku": 100, "nagroda_xp": 100, "nagroda_dukaty": 50, "odznaka_emoji": "❤️" }
        ]
    },
    "dlugosc_streaka": {
        "nazwa_bazowa": "Płomień Aktywności",
        "opis_bazowy": "Utrzymywanie codziennej aktywności.",
        "typ_warunku_bazowy": "dlugosc_streaka",
        "ikona": "🔥",
        "ukryte": False,
        "kategoria_osiagniecia": "Zaangażowanie",
        "tiery": [
            { "id": "streak_3", "nazwa_tieru": "Iskra Codzienności", "opis_tieru": "Utrzymaj aktywność przez 3 dni z rzędu.", "wartosc_warunku": 3, "nagroda_xp": 50, "nagroda_dukaty": 25, "odznaka_emoji": "🕯️" },
            { "id": "streak_7", "nazwa_tieru": "Tygodniowy Płomień", "opis_tieru": "Płomień Twojej aktywności nie gaśnie od tygodnia!", "wartosc_warunku": 7, "nagroda_xp": 150, "nagroda_dukaty": 70, "odznaka_emoji": "🔥" }
        ]
    },
    "wygrane_konkursy": {
        "nazwa_bazowa": "Szczęśliwa Gwiazda",
        "opis_bazowy": "Fortuna Ci sprzyja w konkursach!",
        "typ_warunku_bazowy": "liczba_wygranych_konkursow",
        "ikona": "🌟",
        "ukryte": False,
        "kategoria_osiagniecia": "Szczęście i Los",
        "tiery": [
            { "id": "konkurs_wygrana_1", "nazwa_tieru": "Pierwszy Triumf", "opis_tieru": "Wygraj swój pierwszy konkurs!", "wartosc_warunku": 1, "nagroda_xp": 100, "nagroda_dukaty": 50, "odznaka_emoji": "🏆" },
            { "id": "konkurs_wygrana_5", "nazwa_tieru": "Ulubieniec Fortuny", "opis_tieru": "Pięć razy los uśmiechnął się do Ciebie.", "wartosc_warunku": 5, "nagroda_xp": 300, "nagroda_dukaty": 150, "nagroda_krysztaly": 5, "odznaka_emoji": "🍀" }
        ]
    },
    "uzycie_komend_rozrywka": {
        "nazwa_bazowa": "Dusza Towarzystwa",
        "opis_bazowy": "Korzystanie z komend rozrywkowych.",
        "typ_warunku_bazowy": "liczba_uzyc_komend_kategorii",
        "kategoria_komendy_warunku": "rozrywka",
        "ikona": "🎲",
        "ukryte": False,
        "kategoria_osiagniecia": "Zabawa",
        "tiery": [
            { "id": "fun_komendy_10", "nazwa_tieru": "Animator Zabaw", "opis_tieru": "Użyj 10 komend z kategorii Rozrywka.", "wartosc_warunku": 10, "nagroda_xp": 50, "nagroda_dukaty": 25, "odznaka_emoji": "🥳" },
            { "id": "fun_komendy_50", "nazwa_tieru": "Mistrz Rozrywki", "opis_tieru": "Jesteś ekspertem od dobrej zabawy - 50 użyć komend rozrywkowych!", "wartosc_warunku": 50, "nagroda_xp": 200, "nagroda_dukaty": 100, "odznaka_emoji": "🃏" }
        ]
    },
    "tajemnica_biblioteki": {
        "nazwa_bazowa": "Sekret Starożytnych Zwojów",
        "opis_bazowy": "Odkrycie sekretu ukrytego w najgłębszych zakamarkach wiedzy...",
        "typ_warunku_bazowy": "odkrycie_sekretu_biblioteki",
        "ikona": "🤫",
        "ukryte": True,
        "kategoria_osiagniecia": "Eksploracja",
        "tiery": [
            { "id": "sekret_biblio_1", "nazwa_tieru": "Strażnik Tajemnic", "opis_tieru": "Odkryłeś sekret, który niewielu było dane poznać.", "wartosc_warunku": 1, "nagroda_xp": 1000, "nagroda_dukaty": 500, "odznaka_emoji": "🗝️" }
        ]
    },
     "zakup_krysztalow_osiagniecie": {
        "nazwa_bazowa": "Gwiezdny Inwestor",
        "opis_bazowy": "Wsparcie rozwoju Kronik poprzez nabycie Gwiezdnych Kryształów.",
        "typ_warunku_bazowy": "zakup_krysztalow",
        "ikona": "💠",
        "ukryte": False,
        "kategoria_osiagniecia": "Wsparcie",
        "tiery": [
            { "id": "krysztaly_pierwszy_zakup", "nazwa_tieru": "Patron Skarbca", "opis_tieru": "Dokonaj swojego pierwszego zakupu Gwiezdnych Kryształów.", "wartosc_warunku": 1, "nagroda_xp": 100, "nagroda_dukaty": 50, "odznaka_emoji": "💎" }
        ]
    },
    "szept_elary": {
        "nazwa_bazowa": "Słuchacz Szeptów",
        "opis_bazowy": "Usłyszałeś coś, czego inni nie dostrzegają...",
        "typ_warunku_bazowy": "uzycie_specjalnej_komendy",
        "ikona": "👂",
        "ukryte": True,
        "kategoria_osiagniecia": "Eksploracja",
        "tiery": [
            {
                "id": "szept_elary_1",
                "nazwa_tieru": "Wyostrzony Słuch",
                "opis_tieru": "Udało Ci się usłyszeć pierwszy szept Elary.",
                "wartosc_warunku": 1,
                "nagroda_xp": 250,
                "nagroda_dukaty": 100,
                "odznaka_emoji": "🔮"
            }
        ]
    }
}

# --- Konfiguracja Giveaway ---
GIVEAWAY_EMOJI_DEFAULT: str = "🎉"
GIVEAWAY_COLOR_DEFAULT: discord.Color = discord.Color(0xEE82EE)
GIVEAWAY_CHECK_INTERVAL: int = 30

# --- Konfiguracja Daily Reward ---
ILOSC_DUKATOW_ZA_DAILY: int = 50
COOLDOWN_DAILY_GODZINY: int = 22
COOLDOWN_DAILY_SEKUNDY: int = COOLDOWN_DAILY_GODZINY * 3600

# --- Konfiguracja Komendy "Pracuj" ---
ILOSC_DUKATOW_ZA_PRACE_MIN: int = 10
ILOSC_DUKATOW_ZA_PRACE_MAX: int = 30
COOLDOWN_PRACA_MINUTY: int = 60
COOLDOWN_PRACA_SEKUNDY: int = COOLDOWN_PRACA_MINUTY * 60

# --- Konfiguracja Rankingów Sezonowych (Miesięcznych) ---
ID_KANALU_OGLOSZEN_RANKINGU_MIESIECZNEGO: typing.Optional[int] = 123456789012345678 # ZASTĄP PRAWDZIWYM ID KANAŁU
NAGRODY_RANKINGU_XP_MIESIECZNEGO: dict = {
    1: {"dukaty": 1000, "krysztaly": 50, "rola_id": None, "opis_dodatkowy": "Tytuł Bohatera Miesiąca!"}, # rola_id: ID roli czasowej lub None
    2: {"dukaty": 750, "krysztaly": 30, "rola_id": None},
    3: {"dukaty": 500, "krysztaly": 20, "rola_id": None},
    4: {"dukaty": 250, "krysztaly": 10},
    5: {"dukaty": 100, "krysztaly": 5},
}

# --- Kolory dla Embedów Bota ---
KOLOR_BOT_INFO: discord.Color = discord.Color.blue()
KOLOR_BOT_SUKCES: discord.Color = discord.Color.green()
KOLOR_BOT_OSTRZEZENIE: discord.Color = discord.Color.orange()
KOLOR_BOT_BLAD: discord.Color = discord.Color.red()
KOLOR_BOT_BLAD_KRYTYCZNY: discord.Color = discord.Color.dark_red()
KOLOR_BOT_GLOWNY: discord.Color = discord.Color(0xA78BFA)
KOLOR_POWITALNY: discord.Color = discord.Color(0x8B5CF6)
KOLOR_RANKINGU: discord.Color = discord.Color(0xFFAC33)
KOLOR_RANKINGU_SEZONOWEGO: discord.Color = discord.Color(0xDAA520)


# --- Kolory dla Embedów Pomocy ---
KOLOR_POMOCY_GLOWNY: discord.Color = discord.Color(0x8B5CF6)
KOLOR_POMOCY_KATEGORIA: discord.Color = discord.Color(0xA78BFA)
KOLOR_POMOCY_KOMENDA: discord.Color = discord.Color(0x7C3AED)

# --- Kolory dla Embedów Waluty ---
KOLOR_WALUTY_GLOWNY: discord.Color = discord.Color(0xFFD700)
KOLOR_WALUTY_PREMIUM: discord.Color = discord.Color(0x00BCD4)
KOLOR_SKLEPU_LISTA: discord.Color = discord.Color(0x58D68D)
KOLOR_SKLEPU_PRZEDMIOT: discord.Color = discord.Color(0x48C9B0)
KOLOR_COOLDOWN_WALUTA: discord.Color = discord.Color(0xF39C12)
KOLOR_ADMIN_WALUTA: discord.Color = discord.Color.gold()

# --- Kolory dla Embedów Doświadczenia ---
KOLOR_XP_PROFIL: discord.Color = discord.Color(0xA78BFA)
KOLOR_XP_RANKING: discord.Color = discord.Color.gold()
KOLOR_XP_ADMIN: discord.Color = discord.Color.dark_teal()
KOLOR_XP_OSIAGNIECIE: discord.Color = discord.Color.dark_gold()

# --- Kolory dla Embedów Ogólnych ---
KOLOR_OGOLNY_INFO_GENERAL: discord.Color = discord.Color(0x5DADE2)
KOLOR_OGOLNY_SUKCES_NISKI_PING: discord.Color = discord.Color(0x52BE80)
KOLOR_OGOLNY_OSTRZEZENIE_SREDNI_PING: discord.Color = discord.Color(0xF39C12)
KOLOR_OGOLNY_BLAD_WYSOKI_PING: discord.Color = discord.Color(0xEC7063)
KOLOR_OGOLNY_DOMYSLNY: discord.Color = discord.Color(0x7289DA)

# --- Kolory dla Embedów Właściciela ---
KOLOR_ADMIN_INFO_OWNER: discord.Color = discord.Color.blue()
KOLOR_ADMIN_SUKCES_OWNER: discord.Color = discord.Color.green()
KOLOR_ADMIN_BLAD_OWNER: discord.Color = discord.Color.red()
KOLOR_ADMIN_SPECIAL_OWNER: discord.Color = discord.Color.purple()

# USUNIĘTO: PRZEDMIOTY_SKLEPU - Będą ładowane z bazy danych

# Konfiguracja API i Sklepu Internetowego
API_PORT: int = int(os.getenv("API_PORT", "8080"))
API_KEY: typing.Optional[str] = os.getenv("API_KEY", None)
MAIN_SERVER_ID: typing.Optional[int] = int(os.getenv("MAIN_SERVER_ID")) if os.getenv("MAIN_SERVER_ID") else None

PAKIETY_KRYSZTALOW: dict = {
    "krysztaly_pakiet_100": {
        "nazwa": "Sakiewka Początkującego Maga",
        "ilosc_krysztalow": 100,
        "cena_pln": 4.99,
        "opis": "Mały zastrzyk Gwiezdnych Kryształów na dobry początek.",
        "emoji": "🛍️"
    },
    "krysztaly_pakiet_550": {
        "nazwa": "Mieszek Doświadczonego Alchemika",
        "ilosc_krysztalow": 550,
        "cena_pln": 22.99,
        "opis": "Solidna porcja Kryształów z małym bonusem!",
        "emoji": "💰"
    },
    "krysztaly_pakiet_1200": {
        "nazwa": "Skarbiec Arcymaga",
        "ilosc_krysztalow": 1200,
        "cena_pln": 44.99,
        "opis": "Duży zapas Kryształów dla prawdziwych kolekcjonerów, z atrakcyjnym bonusem!",
        "emoji": "💎"
    }
}
