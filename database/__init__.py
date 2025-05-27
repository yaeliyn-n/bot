"""
Copyright © Krypton 2019-Present - https://github.com/kkrypt0nn (https://krypton.ninja)
Opis:
🐍 Prosty szablon do rozpoczęcia kodowania własnego i spersonalizowanego bota Discord w Pythonie

Wersja: 6.3.0
"""

import aiosqlite
import time
from datetime import datetime, date as date_obj, UTC, timedelta
import json
import typing
import random

if typing.TYPE_CHECKING:
    import discord
    from bot import BotDiscord # Zakładamy, że bot.py jest w głównym katalogu
    import config as bot_config


class ZarzadcaBazyDanych:
    def __init__(self, *, connection: aiosqlite.Connection) -> None:
        self.connection = connection

    # --- Metody ostrzeżeń ---
    async def dodaj_ostrzezenie( self, user_id: int, server_id: int, moderator_id: int, reason: str ) -> int:
        cursor = await self.connection.execute(
            "INSERT INTO warns(user_id, server_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
            (str(user_id), str(server_id), str(moderator_id), reason,),
        )
        await self.connection.commit()
        return typing.cast(int, cursor.lastrowid)

    async def usun_ostrzezenie(self, warn_id: int, user_id: int, server_id: int) -> int:
        await self.connection.execute( "DELETE FROM warns WHERE id=? AND user_id=? AND server_id=?", (warn_id, str(user_id), str(server_id),),)
        await self.connection.commit()
        async with self.connection.execute( "SELECT COUNT(*) FROM warns WHERE user_id=? AND server_id=?", (str(user_id), str(server_id),),) as cursor:
            result = await cursor.fetchone()
            return result[0] if result is not None else 0

    # NOWA METODA: Pobiera pojedyncze ostrzeżenie po jego ID
    async def pobierz_ostrzezenie_po_id(self, warn_id: int) -> tuple | None:
        async with self.connection.execute(
            "SELECT id, user_id, server_id, moderator_id, reason, created_at FROM warns WHERE id = ?",
            (warn_id,)
        ) as cursor:
            return await cursor.fetchone()

    async def pobierz_ostrzezenia(self, user_id: int, server_id: int) -> list:
        async with self.connection.execute( "SELECT id, user_id, server_id, moderator_id, reason, created_at FROM warns WHERE user_id=? AND server_id=?", (str(user_id), str(server_id),),) as cursor:
            result = await cursor.fetchall()
            return list(result)


    # --- Metody Doświadczenia Użytkownika ---
    async def pobierz_doswiadczenie(self, user_id: int, server_id: int) -> tuple | None:
        async with self.connection.execute(
            "SELECT user_id, server_id, xp, poziom, czas_na_glosowym_sekundy, "
            "ostatnia_wiadomosc_timestamp, ostatnia_reakcja_timestamp, "
            "xp_zablokowane_indywidualnie, aktualny_streak_dni, "
            "ostatni_dzien_aktywnosci_streak, liczba_wyslanych_wiadomosci, "
            "liczba_dodanych_reakcji FROM doswiadczenie_uzytkownika "
            "WHERE user_id = ? AND server_id = ?",
            (str(user_id), str(server_id))
        ) as cursor:
            return await cursor.fetchone()

    async def pobierz_lub_stworz_doswiadczenie(self, user_id: int, server_id: int) -> tuple:
        row = await self.pobierz_doswiadczenie(user_id, server_id)
        if row:
            return row

        await self.connection.execute(
            """
            INSERT INTO doswiadczenie_uzytkownika
            (user_id, server_id, xp, poziom, czas_na_glosowym_sekundy,
             ostatnia_wiadomosc_timestamp, ostatnia_reakcja_timestamp,
             xp_zablokowane_indywidualnie, aktualny_streak_dni, ostatni_dzien_aktywnosci_streak,
             liczba_wyslanych_wiadomosci, liczba_dodanych_reakcji)
            VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, NULL, 0, 0)
            """, (str(user_id), str(server_id))
        )
        await self.connection.commit()
        return (str(user_id), str(server_id), 0, 0, 0, 0, 0, 0, 0, None, 0, 0)


    async def aktualizuj_doswiadczenie(
        self, user_id: int, server_id: int,
        xp_dodane: int = 0, nowy_poziom: int | None = None,
        czas_dodany_glosowy: int = 0,
        nowy_timestamp_wiadomosci: int | None = None,
        nowy_timestamp_reakcji: int | None = None,
        nowa_blokada_xp: bool | None = None,
        nowy_streak_dni: int | None = None,
        nowy_ostatni_dzien_streaka_iso: str | None = None,
        inkrementuj_wiadomosci: int = 0,
        inkrementuj_reakcje: int = 0
    ) -> None:
        set_clauses = []
        params = []

        if xp_dodane != 0:
            set_clauses.append("xp = xp + ?")
            params.append(xp_dodane)
        if nowy_poziom is not None:
            set_clauses.append("poziom = ?")
            params.append(nowy_poziom)
        if czas_dodany_glosowy != 0:
            set_clauses.append("czas_na_glosowym_sekundy = czas_na_glosowym_sekundy + ?")
            params.append(czas_dodany_glosowy)
        if nowy_timestamp_wiadomosci is not None:
            set_clauses.append("ostatnia_wiadomosc_timestamp = ?")
            params.append(nowy_timestamp_wiadomosci)
        if nowy_timestamp_reakcji is not None:
            set_clauses.append("ostatnia_reakcja_timestamp = ?")
            params.append(nowy_timestamp_reakcji)
        if nowa_blokada_xp is not None:
            set_clauses.append("xp_zablokowane_indywidualnie = ?")
            params.append(1 if nowa_blokada_xp else 0)
        if nowy_streak_dni is not None:
            set_clauses.append("aktualny_streak_dni = ?")
            params.append(nowy_streak_dni)
        if nowy_ostatni_dzien_streaka_iso is not None or (nowy_streak_dni is not None and nowy_streak_dni == 0) :
            set_clauses.append("ostatni_dzien_aktywnosci_streak = ?")
            params.append(nowy_ostatni_dzien_streaka_iso)
        if inkrementuj_wiadomosci != 0:
            set_clauses.append("liczba_wyslanych_wiadomosci = liczba_wyslanych_wiadomosci + ?")
            params.append(inkrementuj_wiadomosci)
        if inkrementuj_reakcje != 0:
            set_clauses.append("liczba_dodanych_reakcji = liczba_dodanych_reakcji + ?")
            params.append(inkrementuj_reakcje)

        if not set_clauses:
            return

        query = f"UPDATE doswiadczenie_uzytkownika SET {', '.join(set_clauses)} WHERE user_id = ? AND server_id = ?"
        params.extend([str(user_id), str(server_id)])

        await self.connection.execute(query, tuple(params))
        await self.connection.commit()

        # Dodajemy aktualizację miesięcznego XP, jeśli xp_dodane > 0
        if xp_dodane > 0:
            teraz = datetime.now(UTC)
            await self.inkrementuj_miesieczne_xp(str(user_id), str(server_id), teraz.year, teraz.month, xp_dodane)


    async def zresetuj_streak_uzytkownika(self, user_id: int, server_id: int) -> None:
        await self.connection.execute("UPDATE doswiadczenie_uzytkownika SET aktualny_streak_dni = 0, ostatni_dzien_aktywnosci_streak = NULL WHERE user_id = ? AND server_id = ?", (str(user_id), str(server_id)))
        await self.connection.commit()

    # --- Metody Portfela Kronikarza ---
    async def pobierz_portfel(self, user_id: int, server_id: int) -> tuple | None:
        async with self.connection.execute(
            "SELECT user_id, server_id, gwiezdne_dukaty, gwiezdne_krysztaly, ostatnie_odebranie_daily_ts, ostatnia_praca_timestamp FROM portfel_kronikarza WHERE user_id = ? AND server_id = ?",
            (str(user_id), str(server_id))
        ) as cursor:
            return await cursor.fetchone()

    async def pobierz_lub_stworz_portfel(self, user_id: int, server_id: int) -> tuple:
        portfel = await self.pobierz_portfel(user_id, server_id)
        if portfel:
            return portfel
        await self.connection.execute(
            "INSERT INTO portfel_kronikarza (user_id, server_id, gwiezdne_dukaty, gwiezdne_krysztaly, ostatnie_odebranie_daily_ts, ostatnia_praca_timestamp) VALUES (?, ?, 0, 0, 0, 0)",
            (str(user_id), str(server_id))
        )
        await self.connection.commit()
        return (str(user_id), str(server_id), 0, 0, 0, 0)

    async def aktualizuj_portfel(self, user_id: int, server_id: int, ilosc_dukatow_do_dodania: int = 0, ilosc_krysztalow_do_dodania: int = 0, nowy_timestamp_daily: int | None = None, nowy_timestamp_praca: int | None = None) -> tuple[int, int]:
        _, _, obecne_dukaty, obecne_krysztaly, obecny_timestamp_daily, obecny_timestamp_praca = await self.pobierz_lub_stworz_portfel(user_id, server_id)

        nowe_saldo_dukatow = obecne_dukaty + ilosc_dukatow_do_dodania
        nowe_saldo_krysztalow = obecne_krysztaly + ilosc_krysztalow_do_dodania
        timestamp_daily_do_zapisu = nowy_timestamp_daily if nowy_timestamp_daily is not None else obecny_timestamp_daily
        timestamp_praca_do_zapisu = nowy_timestamp_praca if nowy_timestamp_praca is not None else obecny_timestamp_praca


        await self.connection.execute(
            "UPDATE portfel_kronikarza SET gwiezdne_dukaty = ?, gwiezdne_krysztaly = ?, ostatnie_odebranie_daily_ts = ?, ostatnia_praca_timestamp = ? WHERE user_id = ? AND server_id = ?",
            (nowe_saldo_dukatow, nowe_saldo_krysztalow, timestamp_daily_do_zapisu, timestamp_praca_do_zapisu, str(user_id), str(server_id))
        )
        await self.connection.commit()
        return nowe_saldo_dukatow, nowe_saldo_krysztalow

    async def ustaw_saldo_portfela(self, user_id: int, server_id: int, nowe_saldo_dukatow: int | None = None, nowe_saldo_krysztalow: int | None = None) -> tuple[int, int]:
        _, _, obecne_dukaty, obecne_krysztaly, ostatnie_daily_ts_do_zachowania, ostatnia_praca_ts_do_zachowania = await self.pobierz_lub_stworz_portfel(user_id, server_id)

        dukaty_do_zapisu = nowe_saldo_dukatow if nowe_saldo_dukatow is not None else obecne_dukaty
        krysztaly_do_zapisu = nowe_saldo_krysztalow if nowe_saldo_krysztalow is not None else obecne_krysztaly

        await self.connection.execute(
            """
            INSERT INTO portfel_kronikarza (user_id, server_id, gwiezdne_dukaty, gwiezdne_krysztaly, ostatnie_odebranie_daily_ts, ostatnia_praca_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, server_id) DO UPDATE SET
            gwiezdne_dukaty = excluded.gwiezdne_dukaty,
            gwiezdne_krysztaly = excluded.gwiezdne_krysztaly,
            ostatnie_odebranie_daily_ts = portfel_kronikarza.ostatnie_odebranie_daily_ts,
            ostatnia_praca_timestamp = portfel_kronikarza.ostatnia_praca_timestamp
            """,
            (str(user_id), str(server_id), dukaty_do_zapisu, krysztaly_do_zapisu, ostatnie_daily_ts_do_zachowania, ostatnia_praca_ts_do_zachowania)
        )
        await self.connection.commit()
        return dukaty_do_zapisu, krysztaly_do_zapisu

    async def odbierz_codzienna_nagrode(self, user_id: int, server_id: int, ilosc_dukatow_nagrody: int, cooldown_sekundy: int) -> tuple[bool, typing.Union[str, int], int]:
        portfel_dane = await self.pobierz_lub_stworz_portfel(user_id, server_id)
        aktualne_dukaty = portfel_dane[2]
        ostatnie_odebranie_ts = portfel_dane[4]
        teraz_ts = int(time.time())

        if ostatnie_odebranie_ts == 0 or (teraz_ts - ostatnie_odebranie_ts >= cooldown_sekundy):
            nowe_saldo_dukatow, _ = await self.aktualizuj_portfel(user_id, server_id, ilosc_dukatow_do_dodania=ilosc_dukatow_nagrody, nowy_timestamp_daily=teraz_ts)
            return True, f"Otrzymałeś/aś **{ilosc_dukatow_nagrody}** ✨ Gwiezdnych Dukatów!", nowe_saldo_dukatow
        else:
            pozostaly_czas = cooldown_sekundy - (teraz_ts - ostatnie_odebranie_ts)
            return False, pozostaly_czas, aktualne_dukaty

    async def wykonaj_prace(self, user_id: int, server_id: int, min_dukaty: int, max_dukaty: int, cooldown_sekundy: int) -> tuple[bool, typing.Union[str, int], int, int]:
        portfel_dane = await self.pobierz_lub_stworz_portfel(user_id, server_id)
        aktualne_dukaty = portfel_dane[2]
        ostatnia_praca_ts = portfel_dane[5]
        teraz_ts = int(time.time())

        if ostatnia_praca_ts == 0 or (teraz_ts - ostatnia_praca_ts >= cooldown_sekundy):
            zarobione_dukaty = random.randint(min_dukaty, max_dukaty)
            nowe_saldo_dukatow, _ = await self.aktualizuj_portfel(user_id, server_id, ilosc_dukatow_do_dodania=zarobione_dukaty, nowy_timestamp_praca=teraz_ts)
            return True, f"Ciężko pracowałeś i zarobiłeś **{zarobione_dukaty}** ✨ Gwiezdnych Dukatów!", zarobione_dukaty, nowe_saldo_dukatow
        else:
            pozostaly_czas = cooldown_sekundy - (teraz_ts - ostatnia_praca_ts)
            return False, pozostaly_czas, 0, aktualne_dukaty

    # --- Metody Transakcji Premium ---
    async def log_transakcje_premium(self, user_id: str, server_id: str, id_pakietu: str, ilosc_krysztalow: int, cena_pln: float | None, id_platnosci_zewnetrznej: str | None, status: str) -> int:
        timestamp_transakcji = int(time.time())
        cursor = await self.connection.execute(
            """
            INSERT INTO transakcje_premium
            (user_id, server_id, id_pakietu, ilosc_krysztalow, cena_pln, id_platnosci_zewnetrznej, status_platnosci, timestamp_transakcji)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, server_id, id_pakietu, ilosc_krysztalow, cena_pln, id_platnosci_zewnetrznej, status, timestamp_transakcji)
        )
        await self.connection.commit()
        return typing.cast(int, cursor.lastrowid)

    async def aktualizuj_status_transakcji_premium(self, id_transakcji: int, nowy_status: str, id_platnosci_zewnetrznej: str | None = None) -> None:
        updates = ["status_platnosci = ?"]
        params: list[typing.Any] = [nowy_status]
        if id_platnosci_zewnetrznej:
            updates.append("id_platnosci_zewnetrznej = ?")
            params.append(id_platnosci_zewnetrznej)

        params.append(id_transakcji)
        query = f"UPDATE transakcje_premium SET {', '.join(updates)} WHERE id_transakcji = ?"
        await self.connection.execute(query, tuple(params))
        await self.connection.commit()


    # --- Metody Sklepu i Przedmiotów (posiadane przez użytkowników) ---
    async def dodaj_przedmiot_uzytkownika(self, user_id: str, server_id: str, id_przedmiotu_sklepu: str, czas_zakupu_ts: int, czas_wygasniecia_ts: int | None, typ_bonusu: str, wartosc_bonusu: float) -> None:
        await self.connection.execute(
            """
            INSERT INTO posiadane_przedmioty
            (user_id, server_id, id_przedmiotu_sklepu, czas_zakupu_timestamp, czas_wygasniecia_timestamp, typ_bonusu, wartosc_bonusu)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, server_id, id_przedmiotu_sklepu, czas_zakupu_ts, czas_wygasniecia_ts, typ_bonusu, wartosc_bonusu)
        )
        await self.connection.commit()

    async def pobierz_aktywne_zakupione_bonusy_xp_uzytkownika(self, user_id: str, server_id: str) -> list[tuple[str, float, int | None]]:
        teraz_ts = int(time.time())
        query = """
            SELECT typ_bonusu, wartosc_bonusu, czas_wygasniecia_timestamp
            FROM posiadane_przedmioty
            WHERE user_id = ? AND server_id = ? AND typ_bonusu = 'xp_mnoznik'
            AND (czas_wygasniecia_timestamp IS NULL OR czas_wygasniecia_timestamp > ?)
        """
        async with self.connection.execute(query, (user_id, server_id, teraz_ts)) as cursor:
            return await cursor.fetchall() # type: ignore

    async def pobierz_posiadane_przedmioty_uzytkownika(self, user_id: str, server_id: str) -> list[tuple]:
        """Pobiera wszystkie posiadane przedmioty przez użytkownika."""
        query = """
            SELECT p.id_posiadania, p.id_przedmiotu_sklepu, p.czas_zakupu_timestamp, p.czas_wygasniecia_timestamp,
                   p.typ_bonusu, p.wartosc_bonusu, s.name, s.emoji
            FROM posiadane_przedmioty p
            JOIN shop_items s ON p.id_przedmiotu_sklepu = s.id
            WHERE p.user_id = ? AND p.server_id = ?
            ORDER BY p.czas_zakupu_timestamp DESC;
        """
        async with self.connection.execute(query, (user_id, server_id)) as cursor:
            return await cursor.fetchall() # type: ignore

    async def usun_wygasle_posiadane_przedmioty(self) -> int:
        teraz_ts = int(time.time())
        cursor = await self.connection.execute(
            "DELETE FROM posiadane_przedmioty WHERE czas_wygasniecia_timestamp IS NOT NULL AND czas_wygasniecia_timestamp <= ?",
            (teraz_ts,)
        )
        await self.connection.commit()
        return cursor.rowcount

    # --- NOWE METODY: Zarządzanie przedmiotami w sklepie (definicje przedmiotów) ---
    async def dodaj_lub_zaktualizuj_przedmiot_sklepu(self, item_id: str, name: str, description: str, cost_dukaty: typing.Optional[int], cost_krysztaly: typing.Optional[int], emoji: typing.Optional[str], item_type: str, bonus_value: typing.Optional[float], duration_seconds: typing.Optional[int], role_id_to_grant: typing.Optional[str], stock: int) -> None:
        await self.connection.execute(
            """
            INSERT INTO shop_items (id, name, description, cost_dukaty, cost_krysztaly, emoji, item_type, bonus_value, duration_seconds, role_id_to_grant, stock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            cost_dukaty = excluded.cost_dukaty,
            cost_krysztaly = excluded.cost_krysztaly,
            emoji = excluded.emoji,
            item_type = excluded.item_type,
            bonus_value = excluded.bonus_value,
            duration_seconds = excluded.duration_seconds,
            role_id_to_grant = excluded.role_id_to_grant,
            stock = excluded.stock;
            """,
            (item_id, name, description, cost_dukaty, cost_krysztaly, emoji, item_type, bonus_value, duration_seconds, role_id_to_grant, stock)
        )
        await self.connection.commit()

    async def pobierz_przedmiot_sklepu(self, item_id: str) -> tuple | None:
        async with self.connection.execute("SELECT id, name, description, cost_dukaty, cost_krysztaly, emoji, item_type, bonus_value, duration_seconds, role_id_to_grant, stock FROM shop_items WHERE id = ?", (item_id,)) as cursor:
            return await cursor.fetchone()

    async def pobierz_wszystkie_przedmioty_sklepu(self) -> list[tuple]:
        async with self.connection.execute("SELECT id, name, description, cost_dukaty, cost_krysztaly, emoji, item_type, bonus_value, duration_seconds, role_id_to_grant, stock FROM shop_items ORDER BY name ASC") as cursor:
            return await cursor.fetchall() # type: ignore

    async def usun_przedmiot_sklepu(self, item_id: str) -> None:
        await self.connection.execute("DELETE FROM shop_items WHERE id = ?", (item_id,))
        await self.connection.commit()


    # --- Metody Ról Czasowych ---
    async def dodaj_aktywna_role_czasowa(self, user_id: str, server_id: str, rola_id: str, czas_nadania_ts: int, czas_wygasniecia_ts: int, id_przedmiotu_sklepu: typing.Optional[str] = None) -> int:
        query = """
            INSERT INTO aktywne_role_czasowe
            (user_id, server_id, rola_id, id_przedmiotu_sklepu, czas_nadania_timestamp, czas_wygasniecia_timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, server_id, rola_id) DO UPDATE SET
            czas_nadania_timestamp = excluded.czas_nadania_timestamp,
            czas_wygasniecia_timestamp = excluded.czas_wygasniecia_timestamp,
            id_przedmiotu_sklepu = excluded.id_przedmiotu_sklepu
        """
        cursor = await self.connection.execute(query, (user_id, server_id, rola_id, id_przedmiotu_sklepu, czas_nadania_ts, czas_wygasniecia_ts))
        await self.connection.commit()
        return typing.cast(int, cursor.lastrowid)

    async def pobierz_wygasle_role_czasowe(self) -> list[tuple[int, str, str, str, int]]:
        teraz_ts = int(time.time())
        query = """
            SELECT id_wpisu_roli, user_id, server_id, rola_id, czas_wygasniecia_timestamp
            FROM aktywne_role_czasowe
            WHERE czas_wygasniecia_timestamp <= ?
        """
        async with self.connection.execute(query, (teraz_ts,)) as cursor:
            return await cursor.fetchall() # type: ignore

    async def usun_aktywna_role_czasowa_po_id_wpisu(self, id_wpisu_roli: int) -> None:
        await self.connection.execute("DELETE FROM aktywne_role_czasowe WHERE id_wpisu_roli = ?", (id_wpisu_roli,))
        await self.connection.commit()

    async def czy_uzytkownik_ma_aktywna_role_czasowa(self, user_id: str, server_id: str, rola_id: str) -> bool:
        teraz_ts = int(time.time())
        query = """
            SELECT 1 FROM aktywne_role_czasowe
            WHERE user_id = ? AND server_id = ? AND rola_id = ? AND czas_wygasniecia_timestamp > ?
        """
        async with self.connection.execute(query, (user_id, server_id, rola_id, teraz_ts)) as cursor:
            return await cursor.fetchone() is not None

    # --- Metody Osiągnięć ---
    async def oznacz_osiagniecie_jako_zdobyte(self, user_id: str, server_id: str, id_osiagniecia: str) -> bool:
        teraz_ts = int(datetime.now(UTC).timestamp())
        try:
            await self.connection.execute(
                "INSERT INTO zdobyte_osiagniecia_uzytkownika (user_id, server_id, id_osiagniecia, data_zdobycia_timestamp) VALUES (?, ?, ?, ?)",
                (user_id, server_id, id_osiagniecia, teraz_ts)
            )
            await self.connection.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def czy_uzytkownik_zdobyl_osiagniecie(self, user_id: str, server_id: str, id_osiagniecia: str) -> bool:
        async with self.connection.execute("SELECT 1 FROM zdobyte_osiagniecia_uzytkownika WHERE user_id = ? AND server_id = ? AND id_osiagniecia = ?", (user_id, server_id, id_osiagniecia)) as cursor:
            return await cursor.fetchone() is not None

    async def pobierz_zdobyte_osiagniecia_uzytkownika(self, user_id: str, server_id: str) -> list[tuple[str, int]]:
        async with self.connection.execute("SELECT id_osiagniecia, data_zdobycia_timestamp FROM zdobyte_osiagniecia_uzytkownika WHERE user_id = ? AND server_id = ? ORDER BY data_zdobycia_timestamp DESC", (user_id, server_id)) as cursor:
            return await cursor.fetchall() # type: ignore

    # --- Metody Konfiguracji XP ---
    async def ustaw_konfiguracje_xp_kanalu(self, server_id: str, channel_id: str, xp_zablokowane: bool, mnoznik_xp: float):
        await self.connection.execute(
            "INSERT INTO konfiguracja_xp_kanalow (server_id, kanal_id, xp_zablokowane, mnoznik_xp_kanalu) VALUES (?, ?, ?, ?) ON CONFLICT(server_id, kanal_id) DO UPDATE SET xp_zablokowane = excluded.xp_zablokowane, mnoznik_xp_kanalu = excluded.mnoznik_xp_kanalu",
            (server_id, channel_id, 1 if xp_zablokowane else 0, mnoznik_xp)
        )
        await self.connection.commit()

    async def pobierz_konfiguracje_xp_kanalu(self, server_id: str, channel_id: str) -> tuple | None:
        async with self.connection.execute("SELECT xp_zablokowane, mnoznik_xp_kanalu FROM konfiguracja_xp_kanalow WHERE server_id = ? AND kanal_id = ?", (server_id, channel_id)) as cursor:
            return await cursor.fetchone()

    async def usun_konfiguracje_xp_kanalu(self, server_id: str, channel_id: str):
        await self.connection.execute("DELETE FROM konfiguracja_xp_kanalow WHERE server_id = ? AND kanal_id = ?", (server_id, channel_id))
        await self.connection.commit()

    async def pobierz_wszystkie_konfiguracje_xp_kanalow_serwera(self, server_id: str) -> list[tuple[str, bool, float]]:
        async with self.connection.execute("SELECT kanal_id, xp_zablokowane, mnoznik_xp_kanalu FROM konfiguracja_xp_kanalow WHERE server_id = ?", (server_id,)) as cursor:
            rows = await cursor.fetchall()
            return [(row[0], bool(row[1]), row[2]) for row in rows]

    async def ustaw_indywidualna_blokade_xp(self, user_id: int, server_id: int, czy_blokowac: bool):
        await self.connection.execute(
            "UPDATE doswiadczenie_uzytkownika SET xp_zablokowane_indywidualnie = ? WHERE user_id = ? AND server_id = ?",
            (1 if czy_blokowac else 0, str(user_id), str(server_id))
        )
        await self.connection.commit()

    async def ustaw_bonus_xp_roli(self, server_id: str, role_id: str, mnoznik_xp: float):
        await self.connection.execute(
            "INSERT INTO bonusy_xp_rol (server_id, role_id, mnoznik_xp_roli) VALUES (?, ?, ?) ON CONFLICT(server_id, role_id) DO UPDATE SET mnoznik_xp_roli = excluded.mnoznik_xp_roli",
            (server_id, role_id, mnoznik_xp)
        )
        await self.connection.commit()

    async def pobierz_bonusy_xp_rol_serwera(self, server_id: str) -> list[tuple[str, float]]:
        async with self.connection.execute("SELECT rola_id, mnoznik_xp_roli FROM bonusy_xp_rol WHERE server_id = ?", (server_id,)) as cursor:
            return await cursor.fetchall() # type: ignore

    async def usun_bonus_xp_roli(self, server_id: str, role_id: str):
        await self.connection.execute("DELETE FROM bonusy_xp_rol WHERE server_id = ? AND role_id = ?", (server_id, role_id))
        await self.connection.commit()

    # --- Metody Nagród za Poziom ---
    async def dodaj_nagrode_za_poziom(self, server_id: int, poziom: int, rola_id: int) -> None:
        await self.connection.execute(
            "INSERT INTO nagrody_za_poziom (server_id, poziom, rola_id) VALUES (?, ?, ?) ON CONFLICT(server_id, poziom) DO UPDATE SET rola_id = excluded.rola_id",
            (str(server_id), poziom, str(rola_id))
        )
        await self.connection.commit()

    async def usun_nagrode_za_poziom(self, server_id: int, poziom: int) -> None:
        await self.connection.execute("DELETE FROM nagrody_za_poziom WHERE server_id = ? AND poziom = ?", (str(server_id), poziom))
        await self.connection.commit()

    async def pobierz_nagrode_za_poziom(self, server_id: int, poziom: int) -> tuple | None:
        async with self.connection.execute("SELECT rola_id FROM nagrody_za_poziom WHERE server_id = ? AND poziom = ?", (str(server_id), poziom)) as cursor:
            return await cursor.fetchone()

    async def pobierz_wszystkie_nagrody_za_poziom_serwera(self, server_id: int) -> list[tuple[int, str]]:
        async with self.connection.execute("SELECT poziom, rola_id FROM nagrody_za_poziom WHERE server_id = ? ORDER BY poziom ASC", (str(server_id),)) as cursor:
            return await cursor.fetchall() # type: ignore

    # --- Metody Konkursów (Giveaway) ---
    async def stworz_konkurs(self, server_id: str, kanal_id: str, wiadomosc_id: str, tworca_id: str, nagroda: str, liczba_zwyciezcow: int, czas_zakonczenia_ts: int, wymagana_rola_id: str | None = None) -> int:
        czas_rozpoczecia_ts = int(time.time())
        cursor = await self.connection.execute(
            "INSERT INTO aktywne_konkursy (server_id, kanal_id, wiadomosc_id, tworca_id, nagroda, liczba_zwyciezcow, czas_rozpoczecia_ts, czas_zakonczenia_ts, wymagana_rola_id, czy_zakonczony, id_zwyciezcow_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)",
            (server_id, kanal_id, wiadomosc_id, tworca_id, nagroda, liczba_zwyciezcow, czas_rozpoczecia_ts, czas_zakonczenia_ts, wymagana_rola_id)
        )
        await self.connection.commit()
        return typing.cast(int, cursor.lastrowid)

    async def dodaj_uczestnika_konkursu(self, id_konkursu_wiadomosci: str, user_id: str) -> bool:
        try:
            await self.connection.execute("INSERT INTO uczestnicy_konkursow (id_konkursu_wiadomosci, user_id) VALUES (?, ?)", (id_konkursu_wiadomosci, user_id))
            await self.connection.commit()
            return True
        except aiosqlite.IntegrityError: return False

    async def pobierz_uczestnikow_konkursu(self, id_konkursu_wiadomosci: str) -> list[str]:
        async with self.connection.execute("SELECT user_id FROM uczestnicy_konkursow WHERE id_konkursu_wiadomosci = ?", (id_konkursu_wiadomosci,)) as cursor:
            rows = await cursor.fetchall(); return [row[0] for row in rows]

    async def pobierz_zakonczone_konkursy_do_ogloszenia(self) -> list:
        teraz_ts = int(time.time())
        async with self.connection.execute("SELECT * FROM aktywne_konkursy WHERE czy_zakonczony = 0 AND czas_zakonczenia_ts <= ?", (teraz_ts,)) as cursor:
            return await cursor.fetchall() # type: ignore

    async def zakoncz_konkurs(self, id_konkursu_db: int, id_zwyciezcow: list[str]) -> None:
        id_zwyciezcow_json_str = json.dumps(id_zwyciezcow)
        await self.connection.execute("UPDATE aktywne_konkursy SET czy_zakonczony = 1, id_zwyciezcow_json = ? WHERE id_konkursu = ?", (id_zwyciezcow_json_str, id_konkursu_db))
        await self.connection.commit()

    async def pobierz_konkurs_po_wiadomosci_id(self, wiadomosc_id: str) -> tuple | None:
        async with self.connection.execute("SELECT * FROM aktywne_konkursy WHERE wiadomosc_id = ?", (wiadomosc_id,)) as cursor:
            return await cursor.fetchone()

    async def pobierz_aktywne_konkursy_serwera(self, server_id: str) -> list:
        teraz_ts = int(time.time())
        async with self.connection.execute("SELECT * FROM aktywne_konkursy WHERE server_id = ? AND czy_zakonczony = 0 AND czas_zakonczenia_ts > ?", (server_id, teraz_ts)) as cursor:
            return await cursor.fetchall() # type: ignore

    async def pobierz_liczbe_aktywnych_konkursow(self, server_id: str) -> int:
        teraz_ts = int(time.time())
        async with self.connection.execute("SELECT COUNT(*) FROM aktywne_konkursy WHERE server_id = ? AND czy_zakonczony = 0 AND czas_zakonczenia_ts > ?", (server_id, teraz_ts)) as cursor:
            result = await cursor.fetchone(); return result[0] if result else 0

    # --- Metody dla Rankingów ---
    async def pobierz_ranking_xp(self, server_id: int, limit: int = 10) -> list[tuple]:
        async with self.connection.execute("SELECT user_id, xp, poziom FROM doswiadczenie_uzytkownika WHERE server_id = ? ORDER BY xp DESC, poziom DESC LIMIT ?", (str(server_id), limit)) as cursor:
            return await cursor.fetchall() # type: ignore

    async def pobierz_ranking_waluta(self, server_id: int, limit: int = 10, typ_waluty: str = "dukaty") -> list[tuple]:
        kolumna = "gwiezdne_dukaty" if typ_waluty == "dukaty" else "gwiezdne_krysztaly"
        async with self.connection.execute(f"SELECT pk.user_id, pk.{kolumna} FROM portfel_kronikarza pk JOIN doswiadczenie_uzytkownika du ON pk.user_id = du.user_id AND pk.server_id = du.server_id WHERE pk.server_id = ? ORDER BY pk.{kolumna} DESC LIMIT ?", (str(server_id), limit)) as cursor:
            return await cursor.fetchall() # type: ignore

    async def pobierz_ranking_wiadomosci(self, server_id: int, limit: int = 10) -> list[tuple]:
        async with self.connection.execute("SELECT user_id, liczba_wyslanych_wiadomosci FROM doswiadczenie_uzytkownika WHERE server_id = ? ORDER BY liczba_wyslanych_wiadomosci DESC LIMIT ?", (str(server_id), limit)) as cursor:
            return await cursor.fetchall() # type: ignore

    async def pobierz_ranking_czas_glosowy(self, server_id: int, limit: int = 10) -> list[tuple]:
        async with self.connection.execute("SELECT user_id, czas_na_glosowym_sekundy FROM doswiadczenie_uzytkownika WHERE server_id = ? ORDER BY czas_na_glosowym_sekundy DESC LIMIT ?", (str(server_id), limit)) as cursor:
            return await cursor.fetchall() # type: ignore

    async def pobierz_sume_wszystkich_wiadomosci(self, server_id: int) -> int:
        async with self.connection.execute("SELECT SUM(liczba_wyslanych_wiadomosci) FROM doswiadczenie_uzytkownika WHERE server_id = ?", (str(server_id),)) as cursor:
            result = await cursor.fetchone(); return result[0] if result and result[0] is not None else 0

    # --- Metody dla Systemu Misji ---
    async def pobierz_lub_stworz_postep_misji(self, user_id: str, server_id: str, id_misji: str, typ_warunku: str, ostatni_reset_ts_dla_misji: int) -> tuple:
        query_select = "SELECT * FROM postep_misji_uzytkownika WHERE user_id = ? AND server_id = ? AND id_misji = ? AND typ_warunku = ?"
        async with self.connection.execute(query_select, (user_id, server_id, id_misji, typ_warunku)) as cursor:
            row = await cursor.fetchone()

        if row:
            db_ostatni_reset_ts = row[6]
            if db_ostatni_reset_ts < ostatni_reset_ts_dla_misji:
                query_update = "UPDATE postep_misji_uzytkownika SET aktualna_wartosc = 0, ostatni_reset_timestamp = ? WHERE id_postepu = ?"
                await self.connection.execute(query_update, (ostatni_reset_ts_dla_misji, row[0]))
                await self.connection.commit()
                return (row[0], user_id, server_id, id_misji, typ_warunku, 0, ostatni_reset_ts_dla_misji)
            return row # type: ignore
        else:
            query_insert = "INSERT INTO postep_misji_uzytkownika (user_id, server_id, id_misji, typ_warunku, aktualna_wartosc, ostatni_reset_timestamp) VALUES (?, ?, ?, ?, 0, ?)"
            cursor = await self.connection.execute(query_insert, (user_id, server_id, id_misji, typ_warunku, ostatni_reset_ts_dla_misji))
            await self.connection.commit()
            return (cursor.lastrowid, user_id, server_id, id_misji, typ_warunku, 0, ostatni_reset_ts_dla_misji) # type: ignore

    async def aktualizuj_postep_misji(self, user_id: str, server_id: str, id_misji: str, typ_warunku: str, wartosc_do_dodania: int = 1, ustaw_wartosc: typing.Optional[int] = None) -> int:
        if ustaw_wartosc is not None:
            query = "UPDATE postep_misji_uzytkownika SET aktualna_wartosc = ? WHERE user_id = ? AND server_id = ? AND id_misji = ? AND typ_warunku = ?"
            await self.connection.execute(query, (ustaw_wartosc, user_id, server_id, id_misji, typ_warunku))
            nowa_wartosc = ustaw_wartosc
        else:
            query = "UPDATE postep_misji_uzytkownika SET aktualna_wartosc = aktualna_wartosc + ? WHERE user_id = ? AND server_id = ? AND id_misji = ? AND typ_warunku = ?"
            await self.connection.execute(query, (wartosc_do_dodania, user_id, server_id, id_misji, typ_warunku))
            async with self.connection.execute("SELECT aktualna_wartosc FROM postep_misji_uzytkownika WHERE user_id = ? AND server_id = ? AND id_misji = ? AND typ_warunku = ?", (user_id, server_id, id_misji, typ_warunku)) as cursor:
                result = await cursor.fetchone()
                nowa_wartosc = result[0] if result else 0

        await self.connection.commit()
        return nowa_wartosc

    async def oznacz_misje_jako_ukonczona(self, user_id: str, server_id: str, id_misji: str, data_ukonczenia_ts: int) -> None:
        query = "INSERT INTO ukonczone_misje_uzytkownika (user_id, server_id, id_misji, data_ukonczenia_timestamp) VALUES (?, ?, ?, ?)"
        await self.connection.execute(query, (user_id, server_id, id_misji, data_ukonczenia_ts))
        await self.connection.commit()

    async def czy_misja_ukonczona_w_cyklu(self, user_id: str, server_id: str, id_misji: str, poczatek_cyklu_ts: int) -> bool:
        query = "SELECT 1 FROM ukonczone_misje_uzytkownika WHERE user_id = ? AND server_id = ? AND id_misji = ? AND data_ukonczenia_timestamp >= ?"
        async with self.connection.execute(query, (user_id, server_id, id_misji, poczatek_cyklu_ts)) as cursor:
            return await cursor.fetchone() is not None

    async def czy_misja_jednorazowa_ukonczona(self, user_id: str, server_id: str, id_misji: str) -> bool:
        query = "SELECT 1 FROM ukonczone_misje_uzytkownika WHERE user_id = ? AND server_id = ? AND id_misji = ?"
        async with self.connection.execute(query, (user_id, server_id, id_misji)) as cursor:
            return await cursor.fetchone() is not None

    async def pobierz_wszystkie_ukonczone_misje_uzytkownika(self, user_id: str, server_id: str) -> list[tuple[str, int]]:
        query = "SELECT id_misji, data_ukonczenia_timestamp FROM ukonczone_misje_uzytkownika WHERE user_id = ? AND server_id = ? ORDER BY data_ukonczenia_timestamp DESC"
        async with self.connection.execute(query, (user_id, server_id)) as cursor:
            return await cursor.fetchall() # type: ignore

    # --- Metody dla Statystyk Osiągnięć ---
    async def inkrementuj_liczbe_wiadomosci_na_kanale(self, user_id: str, server_id: str, kanal_id: str, ilosc: int = 1) -> int:
        await self.connection.execute(
            """
            INSERT INTO statystyki_aktywnosci_na_kanalach (user_id, server_id, kanal_id, liczba_wiadomosci)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, server_id, kanal_id) DO UPDATE SET
            liczba_wiadomosci = liczba_wiadomosci + excluded.liczba_wiadomosci;
            """, (user_id, server_id, kanal_id, ilosc)
        )
        await self.connection.commit()
        async with self.connection.execute("SELECT liczba_wiadomosci FROM statystyki_aktywnosci_na_kanalach WHERE user_id = ? AND server_id = ? AND kanal_id = ?", (user_id, server_id, kanal_id)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def pobierz_liczbe_wiadomosci_na_kanale(self, user_id: str, server_id: str, kanal_id: str) -> int:
        async with self.connection.execute("SELECT liczba_wiadomosci FROM statystyki_aktywnosci_na_kanalach WHERE user_id = ? AND server_id = ? AND kanal_id = ?", (user_id, server_id, kanal_id)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def inkrementuj_liczbe_wygranych_konkursow(self, user_id: str, server_id: str, ilosc: int = 1) -> int:
        await self.connection.execute(
            """
            INSERT INTO statystyki_konkursow_uzytkownika (user_id, server_id, liczba_wygranych_konkursow)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, server_id) DO UPDATE SET
            liczba_wygranych_konkursow = liczba_wygranych_konkursow + excluded.liczba_wygranych_konkursow;
            """, (user_id, server_id, ilosc)
        )
        await self.connection.commit()
        async with self.connection.execute("SELECT liczba_wygranych_konkursow FROM statystyki_konkursow_uzytkownika WHERE user_id = ? AND server_id = ?", (user_id, server_id)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def pobierz_liczbe_wygranych_konkursow(self, user_id: str, server_id: str) -> int:
        async with self.connection.execute("SELECT liczba_wygranych_konkursow FROM statystyki_konkursow_uzytkownika WHERE user_id = ? AND server_id = ?", (user_id, server_id)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def inkrementuj_uzycia_komend_kategorii(self, user_id: str, server_id: str, nazwa_kategorii: str, ilosc: int = 1) -> int:
        await self.connection.execute(
            """
            INSERT INTO statystyki_uzycia_komend_kategorii (user_id, server_id, nazwa_kategorii, liczba_uzyc)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, server_id, nazwa_kategorii) DO UPDATE SET
            liczba_uzyc = liczba_uzyc + excluded.liczba_uzyc;
            """, (user_id, server_id, nazwa_kategorii, ilosc)
        )
        await self.connection.commit()
        async with self.connection.execute("SELECT liczba_uzyc FROM statystyki_uzycia_komend_kategorii WHERE user_id = ? AND server_id = ? AND nazwa_kategorii = ?", (user_id, server_id, nazwa_kategorii)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def pobierz_uzycia_komend_kategorii(self, user_id: str, server_id: str, nazwa_kategorii: str) -> int:
        async with self.connection.execute("SELECT liczba_uzyc FROM statystyki_uzycia_komend_kategorii WHERE user_id = ? AND server_id = ? AND nazwa_kategorii = ?", (user_id, server_id, nazwa_kategorii)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

    # --- Metody dla Rankingów Sezonowych (Miesięcznych) ---
    async def inkrementuj_miesieczne_xp(self, user_id: str, server_id: str, rok: int, miesiac: int, ilosc_xp: int) -> int:
        """Inkrementuje XP użytkownika w danym miesiącu i zwraca nową sumę miesięcznego XP."""
        await self.connection.execute(
            """
            INSERT INTO miesieczne_xp (user_id, server_id, rok, miesiac, xp_miesieczne)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, server_id, rok, miesiac) DO UPDATE SET
            xp_miesieczne = xp_miesieczne + excluded.xp_miesieczne;
            """, (user_id, server_id, rok, miesiac, ilosc_xp)
        )
        await self.connection.commit()
        async with self.connection.execute("SELECT xp_miesieczne FROM miesieczne_xp WHERE user_id = ? AND server_id = ? AND rok = ? AND miesiac = ?", (user_id, server_id, rok, miesiac)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def pobierz_ranking_miesiecznego_xp(self, server_id: str, rok: int, miesiac: int, limit: int = 10) -> list[tuple[str, int]]:
        """Pobiera ranking użytkowników na podstawie XP zdobytego w danym miesiącu."""
        query = """
            SELECT user_id, xp_miesieczne
            FROM miesieczne_xp
            WHERE server_id = ? AND rok = ? AND miesiac = ?
            ORDER BY xp_miesieczne DESC
            LIMIT ?;
        """
        async with self.connection.execute(query, (server_id, rok, miesiac, limit)) as cursor:
            return await cursor.fetchall() # type: ignore

    async def pobierz_miesieczne_xp_uzytkownika(self, user_id: str, server_id: str, rok: int, miesiac: int) -> int:
        """Pobiera XP zdobyte przez użytkownika w danym miesiącu."""
        async with self.connection.execute("SELECT xp_miesieczne FROM miesieczne_xp WHERE user_id = ? AND server_id = ? AND rok = ? AND miesiac = ?", (user_id, server_id, rok, miesiac)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else 0

    # --- NOWE METODY: Zarządzanie konfiguracją serwera ---
    async def pobierz_konfiguracje_serwera(self, server_id: str) -> dict:
        """Pobiera konfigurację serwera z bazy danych lub zwraca domyślne wartości."""
        query = """
            SELECT xp_blocked_globally, xp_multiplier_event, xp_event_name,
                   welcome_channel_id, default_role_id,
                   live_ranking_channel_id, live_ranking_message_id
            FROM server_config WHERE server_id = ?
        """
        async with self.connection.execute(query, (server_id,)) as cursor:
            row = await cursor.fetchone()

        if row:
            return {
                "xp_blocked_globally": bool(row[0]),
                "xp_multiplier_event": row[1],
                "xp_event_name": row[2],
                "welcome_channel_id": row[3],
                "default_role_id": row[4],
                "live_ranking_channel_id": row[5],
                "live_ranking_message_id": row[6]
            }
        else:
            # Zwróć domyślne wartości, jeśli konfiguracja nie istnieje
            return {
                "xp_blocked_globally": False,
                "xp_multiplier_event": 1.0,
                "xp_event_name": None,
                "welcome_channel_id": None,
                "default_role_id": None,
                "live_ranking_channel_id": None,
                "live_ranking_message_id": None
            }

    async def ustaw_konfiguracje_serwera(self, server_id: str, **kwargs) -> None:
        """
        Ustawia lub aktualizuje konfigurację serwera w bazie danych.
        Używa ON CONFLICT DO UPDATE, aby wstawić lub zaktualizować.
        """
        # Pobierz aktualną konfigurację, aby zachować niezmienione pola
        current_config = await self.pobierz_konfiguracje_serwera(server_id)
        
        # Zaktualizuj tylko te pola, które są przekazane w kwargs
        updated_config = {**current_config, **kwargs}

        await self.connection.execute(
            """
            INSERT INTO server_config (
                server_id, xp_blocked_globally, xp_multiplier_event, xp_event_name,
                welcome_channel_id, default_role_id, live_ranking_channel_id, live_ranking_message_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(server_id) DO UPDATE SET
                xp_blocked_globally = excluded.xp_blocked_globally,
                xp_multiplier_event = excluded.xp_multiplier_event,
                xp_event_name = excluded.xp_event_name,
                welcome_channel_id = excluded.welcome_channel_id,
                default_role_id = excluded.default_role_id,
                live_ranking_channel_id = excluded.live_ranking_channel_id,
                live_ranking_message_id = excluded.live_ranking_message_id
            """,
            (
                server_id,
                1 if updated_config["xp_blocked_globally"] else 0,
                updated_config["xp_multiplier_event"],
                updated_config["xp_event_name"],
                updated_config["welcome_channel_id"],
                updated_config["default_role_id"],
                updated_config["live_ranking_channel_id"],
                updated_config["live_ranking_message_id"]
            )
        )
        await self.connection.commit()

