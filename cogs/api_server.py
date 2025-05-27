# cogs/api_server.py
import asyncio
from aiohttp import web
import discord 
from discord.ext import commands
import time
import typing
import uuid # Do generowania unikalnych ID transakcji dla symulacji
from datetime import datetime, date as date_obj, UTC, timedelta

import config 

if typing.TYPE_CHECKING:
    from bot import BotDiscord # Zakładamy, że bot.py jest w głównym katalogu

class ApiServerCog(commands.Cog, name="apiserver"):
    """📡 Kapsuła zarządzająca serwerem API dla zewnętrznych integracji Kronik Elary."""
    COG_EMOJI = "📡" # Dodajemy emoji dla tego coga

    def __init__(self, bot: 'BotDiscord'):
        self.bot = bot
        self.runner = None

    async def _get_user_details(self, guild: typing.Optional[discord.Guild], user_id: int) -> dict:
        """
        Pobiera szczegóły użytkownika (nazwę, avatar) z obiektu Guild lub globalnie.
        """
        if guild is None:
            try:
                user = await self.bot.fetch_user(user_id)
                if user:
                    return {"username": user.display_name, "avatar_url": str(user.display_avatar.url) if user.display_avatar else None}
            except discord.NotFound:
                pass
            except Exception as e:
                self.bot.logger.error(f"API: Błąd podczas fetch_user (globalnie) dla ID {user_id}: {e}")
            return {"username": f"Nieznany ({user_id})", "avatar_url": None}

        member = guild.get_member(user_id)
        if member:
            return {"username": member.display_name, "avatar_url": str(member.display_avatar.url) if member.display_avatar else None}
        
        # Jeśli nie ma na serwerze, próbujemy globalnie
        try:
            user = await self.bot.fetch_user(user_id)
            if user:
                return {"username": user.display_name, "avatar_url": str(user.display_avatar.url) if user.display_avatar else None}
        except discord.NotFound:
            pass
        except Exception as e:
            self.bot.logger.error(f"API: Błąd podczas fetch_user (po braku na serwerze) dla ID {user_id}: {e}")
        return {"username": f"Nieznany ({user_id})", "avatar_url": None}

    async def start_api_server(self):
        app = web.Application(middlewares=[self.auth_middleware])
        
        # Istniejące endpointy
        app.router.add_get("/api/user_stats/{discord_user_id}", self.get_user_stats_handler)
        app.router.add_get("/api/server_stats", self.get_server_stats_handler)
        app.router.add_get("/api/ranking/xp", self.get_xp_ranking_handler)
        app.router.add_get("/api/ranking/currency", self.get_currency_ranking_handler) 
        app.router.add_get("/api/ranking/premium_currency", self.get_premium_currency_ranking_handler)
        app.router.add_get("/api/ranking/messages", self.get_messages_ranking_handler)
        app.router.add_get("/api/ranking/voicetime", self.get_voicetime_ranking_handler)
        
        # Zaktualizowany endpoint dla sklepu (teraz pobiera z DB bota)
        app.router.add_get("/api/shop/items", self.get_shop_items_handler)
        app.router.add_post("/api/shop/buy/{item_id}", self.post_buy_item_handler)

        app.router.add_get("/api/premium/packages", self.get_premium_packages_handler)
        app.router.add_post("/api/premium/finalize_purchase/{package_id}", self.post_finalize_crystal_purchase_handler) 
        
        # NOWE ENDPOINTY: Zarządzanie Ostrzeżeniami
        app.router.add_post("/api/warnings/add", self.post_add_warning_handler)
        app.router.add_delete("/api/warnings/remove", self.delete_remove_warning_handler)
        app.router.add_get("/api/warnings/list/{guild_id}/{user_id}", self.get_list_warnings_handler)

        # NOWE ENDPOINTY: Wyzwalanie Akcji Bota
        app.router.add_post("/api/actions/send_message", self.post_send_message_handler)

        # NOWE ENDPOINTY: Pobieranie Danych o Misjach
        app.router.add_get("/api/missions/definitions", self.get_missions_definitions_handler)
        app.router.add_get("/api/missions/progress/{guild_id}/{user_id}", self.get_missions_progress_handler)
        # NOWY ENDPOINT: Pobieranie ukończonych misji
        app.router.add_get("/api/missions/completed/{guild_id}/{user_id}", self.get_user_completed_missions_handler)


        # NOWY ENDPOINT: Konfiguracja Bota dla Serwera (pod Dashboard)
        app.router.add_get("/api/config/{guild_id}", self.get_server_config_handler)
        # NOWE ENDPOINTY: Zapisywanie konfiguracji bota
        app.router.add_put("/api/config/{guild_id}/xp", self.put_xp_config_handler)
        app.router.add_put("/api/config/{guild_id}/channel_xp", self.put_channel_xp_config_handler)
        app.router.add_delete("/api/config/{guild_id}/channel_xp/{channel_id}", self.delete_channel_xp_config_handler)
        app.router.add_put("/api/config/{guild_id}/other", self.put_other_config_handler)


        # NOWE ENDPOINTY: Zarządzanie przedmiotami sklepu (dla panelu admina)
        app.router.add_post("/api/admin/shop-items", self.post_create_shop_item_handler)
        app.router.add_put("/api/admin/shop-items/{item_id}", self.put_update_shop_item_handler)
        app.router.add_delete("/api/admin/shop-items/{item_id}", self.delete_shop_item_handler)
        app.router.add_get("/api/admin/shop-items", self.get_admin_shop_items_handler) # Listowanie wszystkich dla admina
        app.router.add_get("/api/admin/shop-items/{item_id}", self.get_admin_shop_item_details_handler) # Pobieranie szczegółów dla admina

        # NOWY ENDPOINT: Pobieranie posiadanych przedmiotów użytkownika
        app.router.add_get("/api/user_inventory/{discord_user_id}", self.get_user_inventory_handler)

        # NOWY ENDPOINT: Pobieranie osiągnięć użytkownika
        app.router.add_get("/api/user_achievements/{guild_id}/{user_id}", self.get_user_achievements_handler)


        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", self.bot.api_port)
        try:
            await site.start()
            self.bot.logger.info(f"Serwer API bota uruchomiony na http://0.0.0.0:{self.bot.api_port}")
        except OSError as e:
            self.bot.logger.error(f"Nie udało się uruchomić serwera API na porcie {self.bot.api_port}: {e}. Port może być zajęty.")
            if self.runner: await self.runner.cleanup()
            self.runner = None

    @web.middleware
    async def auth_middleware(self, request: web.Request, handler):
        """Middleware do autoryzacji żądań API za pomocą klucza API."""
        auth_header = request.headers.get("X-API-Key")
        # Jeśli klucz API nie jest ustawiony w konfiguracji bota, zezwalamy na dostęp (tylko dla developmentu)
        if not self.bot.api_key:
            self.bot.logger.warning(f"API Key nie jest ustawiony. Zezwolono na dostęp do API ({request.path}) bez autoryzacji (TYLKO DEVELOPMENT).")
            return await handler(request)
        
        if auth_header == self.bot.api_key:
            return await handler(request)
        
        self.bot.logger.warning(f"Nieautoryzowana próba dostępu do API z IP: {request.remote}. Klucz: '{auth_header}' dla ścieżki: {request.path}")
        raise web.HTTPUnauthorized(text="Brak autoryzacji: Nieprawidłowy lub brakujący X-API-Key")

    async def get_user_stats_handler(self, request: web.Request):
        """Obsługuje żądanie pobrania statystyk użytkownika."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        if not self.bot.main_server_id: return web.json_response({"error": "MAIN_SERVER_ID nie skonfigurowany"}, status=500)

        discord_user_id_str = request.match_info.get("discord_user_id")
        if not discord_user_id_str or not discord_user_id_str.isdigit():
            return web.json_response({"error": "Nieprawidłowe ID użytkownika"}, status=400)
        
        discord_user_id = int(discord_user_id_str)
        server_id_to_check = self.bot.main_server_id

        try:
            dane_xp_full = await self.bot.baza_danych.pobierz_lub_stworz_doswiadczenie(discord_user_id, server_id_to_check)
            dane_portfela_tuple = await self.bot.baza_danych.pobierz_lub_stworz_portfel(discord_user_id, server_id_to_check)

            gwiezdne_dukaty = dane_portfela_tuple[2]
            gwiezdne_krysztaly = dane_portfela_tuple[3]
            
            stats = {
                "discord_id": discord_user_id, "server_id": server_id_to_check, 
                "level": dane_xp_full[3], "xp": dane_xp_full[2],
                "currency": gwiezdne_dukaty, 
                "premium_currency": gwiezdne_krysztaly,
                "message_count": dane_xp_full[10],
                "voice_time_seconds": dane_xp_full[4], 
                "current_streak_days": dane_xp_full[8],
                "streak_last_active_day_iso": dane_xp_full[9] if dane_xp_full[9] else None,
                "reaction_count": dane_xp_full[11]
            }
            return web.json_response(stats)
        except Exception as e:
            self.bot.logger.error(f"API: Błąd w API (get_user_stats_handler) dla ID {discord_user_id_str}: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera API bota."}, status=500)


    async def get_server_stats_handler(self, request: web.Request):
        """Obsługuje żądanie pobrania statystyk serwera."""
        if self.bot.baza_danych is None or not self.bot.main_server_id:
            return web.json_response({"error": "Usługa statystyk serwera jest niedostępna"}, status=503)

        guild = self.bot.get_guild(self.bot.main_server_id)
        if not guild:
            return web.json_response({"error": "Nie można znaleźć głównego serwera"}, status=500)

        try:
            total_members = guild.member_count
            online_members = sum(1 for m in guild.members if m.status != discord.Status.offline)
            total_messages = await self.bot.baza_danych.pobierz_sume_wszystkich_wiadomosci(self.bot.main_server_id)
            active_giveaways = await self.bot.baza_danych.pobierz_liczbe_aktywnych_konkursow(str(self.bot.main_server_id))
            stats = {
                "total_members": total_members, "online_members": online_members,
                "total_messages": total_messages, "active_giveaways": active_giveaways
            }
            return web.json_response(stats)
        except Exception as e:
            self.bot.logger.error(f"Błąd w API (get_server_stats_handler): {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd API przy statystykach serwera."}, status=500)

    async def _get_ranking_data(self, db_method_name: str, value_key_in_response: str, limit: int = 10, typ_waluty_ranking: str | None = None):
        """Pomocnicza funkcja do pobierania danych rankingowych."""
        if self.bot.baza_danych is None: raise web.HTTPServiceUnavailable(text="Baza danych niedostępna")
        server_id = self.bot.main_server_id
        if not server_id: raise web.HTTPInternalServerError(text="MAIN_SERVER_ID nie skonfigurowany")
        guild = self.bot.get_guild(server_id) # Może być None, jeśli bot nie jest na serwerze
        
        db_method = getattr(self.bot.baza_danych, db_method_name)
        
        if typ_waluty_ranking:
             raw_ranking_data = await db_method(server_id, limit, typ_waluty_ranking)
        else:
             raw_ranking_data = await db_method(server_id, limit)
        
        ranking_response = []
        for entry in raw_ranking_data:
            user_id = entry[0]
            score = entry[1]
            user_details = await self._get_user_details(guild, user_id) # Przekazujemy potencjalnie None guild
            user_data = {"user_id": user_id, "username": user_details["username"], "avatar_url": user_details["avatar_url"], value_key_in_response: score}
            if db_method_name == "pobierz_ranking_xp" and len(entry) > 2: user_data["level"] = entry[2]
            ranking_response.append(user_data)
        return ranking_response

    async def get_xp_ranking_handler(self, request: web.Request):
        """Obsługuje żądanie pobrania rankingu XP."""
        try:
            limit = int(request.query.get("limit", 10))
            if not (1 <= limit <= 50): limit = 10
            ranking_data = await self._get_ranking_data("pobierz_ranking_xp", "xp_total", limit=limit)
            return web.json_response(ranking_data)
        except Exception as e:
            self.bot.logger.error(f"Błąd w API (get_xp_ranking_handler): {e}", exc_info=True)
            return web.json_response({"error": f"Wewnętrzny błąd serwera API przy pobieraniu rankingu XP: {str(e)}"}, status=500)

    async def get_currency_ranking_handler(self, request: web.Request):
        """Obsługuje żądanie pobrania rankingu Gwiezdnych Dukatów."""
        try:
            limit = int(request.query.get("limit", 10))
            if not (1 <= limit <= 50): limit = 10
            ranking_data = await self._get_ranking_data("pobierz_ranking_waluta", "currency_balance", limit=limit, typ_waluty_ranking="dukaty")
            return web.json_response(ranking_data)
        except Exception as e:
            self.bot.logger.error(f"Błąd w API (get_currency_ranking_handler - dukaty): {e}", exc_info=True)
            return web.json_response({"error": f"Wewnętrzny błąd API przy rankingu Gwiezdnych Dukatów: {str(e)}"}, status=500)

    async def get_premium_currency_ranking_handler(self, request: web.Request):
        """Obsługuje żądanie pobrania rankingu waluty premium."""
        try:
            limit = int(request.query.get("limit", 10))
            if not (1 <= limit <= 50): limit = 10
            ranking_data = await self._get_ranking_data("pobierz_ranking_waluta", "premium_currency_balance", limit=limit, typ_waluty_ranking="krysztaly")
            return web.json_response(ranking_data)
        except Exception as e:
            self.bot.logger.error(f"Błąd w API (get_premium_currency_ranking_handler - krysztaly): {e}", exc_info=True)
            return web.json_response({"error": f"Wewnętrzny błąd API przy rankingu {config.NAZWA_WALUTY_PREMIUM}: {str(e)}"}, status=500)


    async def get_messages_ranking_handler(self, request: web.Request):
        """Obsługuje żądanie pobrania rankingu wiadomości."""
        try:
            limit = int(request.query.get("limit", 10))
            if not (1 <= limit <= 50): limit = 10
            ranking_data = await self._get_ranking_data("pobierz_ranking_wiadomosci", "message_count", limit=limit)
            return web.json_response(ranking_data)
        except Exception as e:
            self.bot.logger.error(f"Błąd w API (get_messages_ranking_handler): {e}", exc_info=True)
            return web.json_response({"error": f"Wewnętrzny błąd API przy rankingu wiadomości: {str(e)}"}, status=500)

    async def get_voicetime_ranking_handler(self, request: web.Request):
        """Obsługuje żądanie pobrania rankingu czasu na kanale głosowym."""
        try:
            limit = int(request.query.get("limit", 10))
            if not (1 <= limit <= 50): limit = 10
            ranking_data = await self._get_ranking_data("pobierz_ranking_czas_glosowy", "voice_time_seconds", limit=limit)
            return web.json_response(ranking_data)
        except Exception as e:
            self.bot.logger.error(f"Błąd w API (get_voicetime_ranking_handler): {e}", exc_info=True)
            return web.json_response({"error": f"Wewnętrzny błąd API przy rankingu czasu głosowego: {str(e)}"}, status=500)

    async def get_shop_items_handler(self, request: web.Request):
        """
        Obsługuje żądanie pobrania listy przedmiotów ze sklepu (dla użytkowników).
        Pobiera dane z bazy danych bota.
        """
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        try:
            shop_items_db = await self.bot.baza_danych.pobierz_wszystkie_przedmioty_sklepu()
            shop_items_processed = []
            for item_tuple in shop_items_db:
                # id, name, description, cost_dukaty, cost_krysztaly, emoji, item_type, bonus_value, duration_seconds, role_id_to_grant, stock
                shop_items_processed.append({
                    "id": item_tuple[0],
                    "name": item_tuple[1],
                    "description": item_tuple[2],
                    "cost_dukaty": item_tuple[3],
                    "cost_krysztaly": item_tuple[4],
                    "emoji": item_tuple[5],
                    "item_type": item_tuple[6],
                    "bonus_value": item_tuple[7],
                    "duration_seconds": item_tuple[8],
                    "role_id_to_grant": item_tuple[9],
                    "stock": item_tuple[10]
                })
            return web.json_response(shop_items_processed)
        except Exception as e:
            self.bot.logger.error(f"API: Błąd w get_shop_items_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera przy pobieraniu przedmiotów sklepu."}, status=500)


    async def post_buy_item_handler(self, request: web.Request):
        """Obsługuje żądanie zakupu przedmiotu ze sklepu."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        if not self.bot.main_server_id: return web.json_response({"error": "MAIN_SERVER_ID nie skonfigurowany"}, status=500)

        item_id_str = request.match_info.get("item_id")
        if not item_id_str: return web.json_response({"error": "Nie podano ID przedmiotu"}, status=400)

        try:
            data = await request.json()
            discord_user_id_str = data.get("discord_user_id")
            currency_type_from_request = data.get("currency_type", "dukaty") 

            if not discord_user_id_str or not str(discord_user_id_str).isdigit():
                return web.json_response({"error": "Nieprawidłowe ID użytkownika"}, status=400)
            discord_user_id = int(discord_user_id_str)
        except Exception:
            return web.json_response({"error": "Nieprawidłowy format danych (oczekiwano JSON z discord_user_id i opcjonalnie currency_type)"}, status=400)

        server_id_to_check = self.bot.main_server_id
        
        # Pobierz przedmiot z bazy danych, a nie z config.PRZEDMIOTY_SKLEPU
        item_data_tuple = await self.bot.baza_danych.pobierz_przedmiot_sklepu(item_id_str)
        if not item_data_tuple: return web.json_response({"error": f"Przedmiot '{item_id_str}' nie istnieje"}, status=404)

        # Konwertuj krotkę na słownik dla łatwiejszego dostępu
        item_data = {
            "id": item_data_tuple[0], "name": item_data_tuple[1], "description": item_data_tuple[2],
            "cost_dukaty": item_data_tuple[3], "cost_krysztaly": item_data_tuple[4], "emoji": item_data_tuple[5],
            "item_type": item_data_tuple[6], "bonus_value": item_data_tuple[7], "duration_seconds": item_data_tuple[8],
            "role_id_to_grant": item_data_tuple[9], "stock": item_data_tuple[10]
        }

        koszt_dukaty = item_data.get("cost_dukaty")
        koszt_krysztaly = item_data.get("cost_krysztaly")
        
        koszt_finalny = 0
        waluta_do_odjecia = "" 

        if currency_type_from_request == "dukaty" and koszt_dukaty is not None:
            koszt_finalny = koszt_dukaty
            waluta_do_odjecia = "dukaty"
        elif currency_type_from_request == "krysztaly" and koszt_krysztaly is not None:
            koszt_finalny = koszt_krysztaly
            waluta_do_odjecia = "krysztaly"
        elif koszt_dukaty is not None: 
            koszt_finalny = koszt_dukaty
            waluta_do_odjecia = "dukaty"
        elif koszt_krysztaly is not None: 
            koszt_finalny = koszt_krysztaly
            waluta_do_odjecia = "krysztaly"
        else:
            return web.json_response({"error": f"Przedmiot '{item_data['name']}' nie ma ustalonej ceny w wybranej walucie lub w ogóle."}, status=400)

        # Sprawdzenie stanu magazynowego
        if item_data["stock"] != -1 and item_data["stock"] <= 0:
            return web.json_response({"error": f"Przedmiot '{item_data['name']}' jest wyprzedany."}, status=409) # Conflict

        try:
            portfel_dane = await self.bot.baza_danych.pobierz_lub_stworz_portfel(discord_user_id, server_id_to_check)
            aktualne_dukaty = portfel_dane[2]
            aktualne_krysztaly = portfel_dane[3]

            posiadana_ilosc_waluty = aktualne_dukaty if waluta_do_odjecia == "dukaty" else aktualne_krysztaly

            if posiadana_ilosc_waluty < koszt_finalny:
                nazwa_waluty_braku = "Gwiezdnych Dukatów" if waluta_do_odjecia == "dukaty" else config.NAZWA_WALUTY_PREMIUM
                return web.json_response({
                    "error": f"Niewystarczająca ilość {nazwa_waluty_braku}.",
                    "current_balance": posiadana_ilosc_waluty, "item_cost": koszt_finalny
                }, status=402) # Payment Required

            nowe_saldo_dukatow, nowe_saldo_krysztalow = aktualne_dukaty, aktualne_krysztaly
            if waluta_do_odjecia == "dukaty":
                nowe_saldo_dukatow, nowe_saldo_krysztalow = await self.bot.baza_danych.aktualizuj_portfel(discord_user_id, server_id_to_check, ilosc_dukatow_do_dodania=-koszt_finalny)
            else: 
                nowe_saldo_dukatow, nowe_saldo_krysztalow = await self.bot.baza_danych.aktualizuj_portfel(discord_user_id, server_id_to_check, ilosc_krysztalow_do_dodania=-koszt_finalny)
            
            # Zmniejsz stan magazynowy, jeśli nie jest nieskończony
            if item_data["stock"] != -1:
                await self.bot.baza_danych.dodaj_lub_zaktualizuj_przedmiot_sklepu(
                    item_data["id"], item_data["name"], item_data["description"],
                    item_data["cost_dukaty"], item_data["cost_krysztaly"], item_data["emoji"],
                    item_data["item_type"], item_data["bonus_value"], item_data["duration_seconds"],
                    item_data["role_id_to_grant"], item_data["stock"] - 1 # Zmniejsz stock
                )

            czas_zakupu_ts = int(time.time())
            czas_wygasniecia_ts = None
            if item_data.get("duration_seconds"):
                czas_wygasniecia_ts = czas_zakupu_ts + item_data["duration_seconds"]
            
            typ_bonusu_przedmiotu = item_data.get("item_type", "unknown")
            wartosc_bonusu_do_zapisu = item_data.get("bonus_value", 0.0)

            # Specjalna obsługa dla timed_role
            if typ_bonusu_przedmiotu == "timed_role":
                rola_id_str = item_data.get("role_id_to_grant")
                if not rola_id_str:
                    raise ValueError("Brak role_id_to_grant dla przedmiotu typu timed_role.")
                
                guild_obj = self.bot.get_guild(server_id_to_check)
                member = guild_obj.get_member(discord_user_id) if guild_obj else None
                rola_obj = guild_obj.get_role(int(rola_id_str)) if guild_obj and rola_id_str.isdigit() else None

                if member and rola_obj:
                    await member.add_roles(rola_obj, reason=f"Zakup przedmiotu w sklepie (API): {item_data['name']}")
                    await self.bot.baza_danych.dodaj_aktywna_role_czasowa(
                        str(discord_user_id), str(server_id_to_check), str(rola_obj.id),
                        czas_zakupu_ts, czas_wygasniecia_ts, item_id_str
                    )
                    self.bot.logger.info(f"API: Przyznano rolę '{rola_obj.name}' użytkownikowi {member.display_name} po zakupie '{item_data['name']}'.")
                else:
                    self.bot.logger.warning(f"API: Nie można nadać roli {rola_id_str} użytkownikowi {discord_user_id} po zakupie. Member lub rola nie znaleziona.")
                    # Nadal dodajemy przedmiot do posiadanych, nawet jeśli rola nie została nadana
                    await self.bot.baza_danych.dodaj_przedmiot_uzytkownika(
                        str(discord_user_id), str(server_id_to_check), item_id_str,
                        czas_zakupu_ts, czas_wygasniecia_ts,
                        typ_bonusu_przedmiotu, wartosc_bonusu_do_zapisu
                    )
            else:
                await self.bot.baza_danych.dodaj_przedmiot_uzytkownika(
                    str(discord_user_id), str(server_id_to_check), item_id_str,
                    czas_zakupu_ts, czas_wygasniecia_ts,
                    typ_bonusu_przedmiotu, wartosc_bonusu_do_zapisu
                )

            self.bot.logger.info(f"API: Użytkownik {discord_user_id} zakupił '{item_data['name']}' za {koszt_finalny} ({waluta_do_odjecia}).")
            return web.json_response({
                "success": True, "message": f"Pomyślnie zakupiono: {item_data['name']}!",
                "new_balance_dukaty": nowe_saldo_dukatow, "new_balance_krysztaly": nowe_saldo_krysztalow,
                "item_purchased": item_id_str
            })
        except Exception as e:
            self.bot.logger.error(f"API: Błąd zakupu '{item_id_str}' przez {discord_user_id}: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera przy zakupie."}, status=500)


    async def get_premium_packages_handler(self, request: web.Request):
        """Obsługuje żądanie pobrania listy pakietów premium (kryształów)."""
        return web.json_response(config.PAKIETY_KRYSZTALOW)

    async def post_finalize_crystal_purchase_handler(self, request: web.Request):
        """Obsługuje żądanie finalizacji zakupu pakietu kryształów."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        if not self.bot.main_server_id: return web.json_response({"error": "MAIN_SERVER_ID nie skonfigurowany"}, status=500)

        package_id_str = request.match_info.get("package_id")
        if not package_id_str: return web.json_response({"error": "Nie podano ID pakietu"}, status=400)

        try:
            data = await request.json()
            discord_user_id_str = data.get("discord_user_id")
            transaction_id = data.get("transaction_id") 

            if not discord_user_id_str or not str(discord_user_id_str).isdigit():
                return web.json_response({"error": "Nieprawidłowe ID użytkownika"}, status=400)
            if not transaction_id:
                return web.json_response({"error": "Brak identyfikatora transakcji (transaction_id)"}, status=400)
            
            discord_user_id = int(discord_user_id_str)
        except Exception:
            return web.json_response({"error": "Nieprawidłowy format danych (oczekiwano JSON z discord_user_id i transaction_id)"}, status=400)

        
        server_id_to_check = self.bot.main_server_id
        package_data = config.PAKIETY_KRYSZTALOW.get(package_id_str)

        if not package_data:
            return web.json_response({"error": f"Pakiet '{package_id_str}' nie istnieje."}, status=404)

        ilosc_krysztalow_do_dodania = package_data.get("ilosc_krysztalow", 0)
        cena_pln_pakietu = package_data.get("cena_pln")

        try:
            _, nowe_saldo_krysztalow = await self.bot.baza_danych.aktualizuj_portfel(
                discord_user_id, server_id_to_check, ilosc_krysztalow_do_dodania=ilosc_krysztalow_do_dodania
            )
            
            # Logowanie transakcji
            db_transaction_id = await self.bot.baza_danych.log_transakcje_premium(
                str(discord_user_id), str(server_id_to_check), package_id_str, 
                ilosc_krysztalow_do_dodania, cena_pln_pakietu, 
                transaction_id, 
                "zrealizowana" 
            )

            # Sprawdzenie osiągnięcia za pierwszy zakup
            guild_obj = self.bot.get_guild(server_id_to_check)
            if guild_obj:
                member = guild_obj.get_member(discord_user_id)
                if member:
                    await self.bot.sprawdz_i_przyznaj_osiagniecia(member, guild_obj, "zakup_krysztalow", 1)


            self.bot.logger.info(f"API: Użytkownik {discord_user_id} otrzymał pakiet '{package_data['nazwa']}' ({ilosc_krysztalow_do_dodania} {config.SYMBOL_WALUTY_PREMIUM}) po transakcji {transaction_id} (DB ID: {db_transaction_id}).")
            return web.json_response({
                "success": True, 
                "message": f"Pomyślnie przyznano pakiet: {package_data['nazwa']}! Dodano {ilosc_krysztalow_do_dodania} {config.SYMBOL_WALUTY_PREMIUM}.",
                "new_premium_currency_balance": nowe_saldo_krysztalow,
                "package_id": package_id_str,
                "transaction_id": transaction_id
            })
        except Exception as e:
            self.bot.logger.error(f"API: Błąd finalizacji zakupu pakietu '{package_id_str}' (transakcja {transaction_id}) przez {discord_user_id}: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera przy finalizacji zakupu kryształów."}, status=500)

    # --- NOWE ENDPOINTY ---

    async def post_add_warning_handler(self, request: web.Request):
        """Obsługuje dodawanie ostrzeżenia przez API."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        
        try:
            data = await request.json()
            guild_id_str = data.get("guild_id")
            user_id_str = data.get("user_id")
            moderator_id_str = data.get("moderator_id")
            reason = data.get("reason")

            if not all([guild_id_str, user_id_str, moderator_id_str, reason]):
                return web.json_response({"error": "Brakujące pola: guild_id, user_id, moderator_id, reason"}, status=400)
            if not (guild_id_str.isdigit() and user_id_str.isdigit() and moderator_id_str.isdigit()):
                return web.json_response({"error": "Nieprawidłowe formaty ID (oczekiwano cyfr)"}, status=400)

            guild_id = int(guild_id_str)
            user_id = int(user_id_str)
            moderator_id = int(moderator_id_str)

            guild = self.bot.get_guild(guild_id)
            if not guild:
                return web.json_response({"error": "Serwer nie znaleziony"}, status=404)
            
            member = guild.get_member(user_id)
            if not member:
                try: # Spróbuj pobrać użytkownika globalnie, jeśli nie jest członkiem serwera
                    user_obj = await self.bot.fetch_user(user_id)
                    # Jeśli użytkownik istnieje globalnie, ale nie na serwerze, nadal możemy dodać ostrzeżenie w bazie
                    # ale nie wyślemy DM ani nie sprawdzimy ról serwerowych.
                except discord.NotFound:
                    return web.json_response({"error": "Użytkownik nie znaleziony na serwerze"}, status=404)
                except Exception as e:
                    self.bot.logger.error(f"API: Błąd fetch_user dla {user_id}: {e}", exc_info=True)
                    return web.json_response({"error": "Wewnętrzny błąd podczas pobierania użytkownika"}, status=500)


            warn_id = await self.bot.baza_danych.dodaj_ostrzezenie(user_id, guild_id, moderator_id, reason)
            all_warnings = await self.bot.baza_danych.pobierz_ostrzezenia(user_id, guild_id)
            total_warnings = len(all_warnings)

            # Opcjonalnie: wysłanie DM do użytkownika
            if member: # Jeśli to Member, a nie tylko User
                try:
                    await member.send(f"Zostałeś/aś ostrzeżony/a na serwerze **{guild.name}**!\nPowód: {reason}\nTo Twoje {total_warnings}. ostrzeżenie.")
                except discord.Forbidden:
                    self.bot.logger.warning(f"API Warn: Nie można wysłać DM do {member.display_name} o ostrzeżeniu.")

            self.bot.logger.info(f"API: Dodano ostrzeżenie #{warn_id} dla {user_id} na {guild_id} przez {moderator_id}.")
            return web.json_response({
                "success": True,
                "message": "Ostrzeżenie dodane pomyślnie.",
                "warn_id": warn_id,
                "user_total_warnings": total_warnings
            })
        except Exception as e:
            self.bot.logger.error(f"API: Błąd w post_add_warning_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def delete_remove_warning_handler(self, request: web.Request):
        """Obsługuje usuwanie ostrzeżenia przez API."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)

        try:
            data = await request.json()
            warn_id_str = data.get("warn_id")

            if not warn_id_str or not warn_id_str.isdigit():
                return web.json_response({"error": "Nieprawidłowe ID ostrzeżenia"}, status=400)
            
            warn_id = int(warn_id_str)
            
            # Pobierz ostrzeżenie, aby uzyskać user_id i server_id
            warning_data = await self.bot.baza_danych.pobierz_ostrzezenie_po_id(warn_id)
            if not warning_data:
                return web.json_response({"error": f"Ostrzeżenie o ID {warn_id} nie znaleziono."}, status=404)

            user_id = int(warning_data[1])
            server_id = int(warning_data[2])

            remaining_warnings_count = await self.bot.baza_danych.usun_ostrzezenie(warn_id, user_id, server_id)

            self.bot.logger.info(f"API: Usunięto ostrzeżenie #{warn_id} dla {user_id} na {server_id}.")
            return web.json_response({
                "success": True,
                "message": f"Ostrzeżenie o ID {warn_id} usunięte pomyślnie.",
                "user_id": user_id,
                "guild_id": server_id,
                "user_total_warnings_remaining": remaining_warnings_count
            })
        except Exception as e:
            self.bot.logger.error(f"API: Błąd w delete_remove_warning_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def get_list_warnings_handler(self, request: web.Request):
        """Obsługuje listowanie ostrzeżeń dla użytkownika przez API."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)

        guild_id_str = request.match_info.get("guild_id")
        user_id_str = request.match_info.get("user_id")

        if not all([guild_id_str, user_id_str]) or not (guild_id_str.isdigit() and user_id_str.isdigit()):
            return web.json_response({"error": "Nieprawidłowe ID serwera lub użytkownika"}, status=400)

        guild_id = int(guild_id_str)
        user_id = int(user_id_str)

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "Serwer nie znaleziony"}, status=404)
        
        try:
            warnings_db = await self.bot.baza_danych.pobierz_ostrzezenia(user_id, guild_id)
            warnings_list = []
            for warn_id, _, _, moderator_id_db, reason_db, created_at_db in warnings_db:
                moderator_details = await self._get_user_details(guild, int(moderator_id_db))
                
                # Formatowanie daty na ISO 8601
                created_at_dt = None
                if isinstance(created_at_db, str):
                    try:
                        # Zakładamy format 'YYYY-MM-DD HH:MM:SS' z SQLite
                        created_at_dt = datetime.strptime(created_at_db, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                    except ValueError:
                         # Jeśli parsowanie się nie uda, próbujemy jako timestamp (jeśli to int)
                        try: created_at_dt = datetime.fromtimestamp(int(created_at_db), UTC)
                        except: pass
                elif isinstance(created_at_db, (int, float)):
                    created_at_dt = datetime.fromtimestamp(created_at_db, UTC)
                
                warnings_list.append({
                    "warn_id": warn_id,
                    "moderator_id": moderator_id_db,
                    "moderator_username": moderator_details["username"],
                    "reason": reason_db,
                    "created_at_utc": created_at_dt.isoformat() if created_at_dt else None
                })
            
            self.bot.logger.info(f"API: Wysłano listę ostrzeżeń dla {user_id} na {guild_id}.")
            return web.json_response({
                "success": True,
                "user_id": user_id,
                "guild_id": guild_id,
                "warnings": warnings_list
            })
        except Exception as e:
            self.bot.logger.error(f"API: Błąd w get_list_warnings_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def post_send_message_handler(self, request: web.Request):
        """Obsługuje wysyłanie wiadomości/ogłoszeń przez API."""
        try:
            data = await request.json()
            guild_id_str = data.get("guild_id")
            channel_id_str = data.get("channel_id")
            message_content = data.get("message_content")
            embed_data = data.get("embed") # Opcjonalny embed

            if not all([guild_id_str, channel_id_str]) or not (guild_id_str.isdigit() and channel_id_str.isdigit()):
                return web.json_response({"error": "Nieprawidłowe ID serwera lub kanału"}, status=400)
            if not message_content and not embed_data:
                return web.json_response({"error": "Brak treści wiadomości lub danych embed"}, status=400)

            guild_id = int(guild_id_str)
            channel_id = int(channel_id_str)

            guild = self.bot.get_guild(guild_id)
            if not guild:
                return web.json_response({"error": "Serwer nie znaleziony"}, status=404)
            
            channel = guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                return web.json_response({"error": "Kanał nie znaleziony lub nie jest kanałem tekstowym"}, status=404)

            # Sprawdzenie uprawnień bota
            if not channel.permissions_for(guild.me).send_messages:
                return web.json_response({"error": "Bot nie ma uprawnień do wysyłania wiadomości na tym kanale"}, status=403)
            
            discord_embed = None
            if embed_data:
                try:
                    discord_embed = discord.Embed.from_dict(embed_data)
                except Exception as e:
                    return web.json_response({"error": f"Nieprawidłowy format embedu: {e}"}, status=400)

            sent_message = await channel.send(content=message_content, embed=discord_embed)
            
            self.bot.logger.info(f"API: Wysłano wiadomość na kanale {channel_id} w serwerze {guild_id}.")
            return web.json_response({
                "success": True,
                "message": "Wiadomość wysłana pomyślnie.",
                "message_id": str(sent_message.id),
                "channel_id": str(sent_message.channel.id),
                "guild_id": str(sent_message.guild.id)
            })
        except discord.Forbidden:
            self.bot.logger.error(f"API: Bot nie ma uprawnień do wysłania wiadomości.")
            return web.json_response({"error": "Brak uprawnień bota do wykonania tej akcji."}, status=403)
        except Exception as e:
            self.bot.logger.error(f"API: Błąd w post_send_message_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def get_missions_definitions_handler(self, request: web.Request):
        """Obsługuje pobieranie definicji misji przez API."""
        if not self.bot.DEFINICJE_MISJI:
            return web.json_response({"success": True, "missions": {}}, status=200)
        
        # Tworzymy kopię, aby uniknąć modyfikacji oryginalnego słownika i upewnić się, że jest serializowalny
        missions_data = {}
        for mission_id, mission_def in self.bot.DEFINICJE_MISJI.items():
            # Usuwamy potencjalnie niezserializowalne obiekty, jeśli takie są, lub formatujemy
            # Na przykład, jeśli nagrody zawierają obiekty Discorda, należy je przekształcić
            
            # Prosta kopia, zakładając, że DEFINICJE_MISJI są już w większości serializowalne
            # Można dodać bardziej złożoną logikę, jeśli DEFINICJE_MISJI będą zawierać np. obiekty Discord.Role
            missions_data[mission_id] = mission_def 
        
        self.bot.logger.info("API: Wysłano definicje misji.")
        return web.json_response({
            "success": True,
            "missions": missions_data
        })

    async def get_missions_progress_handler(self, request: web.Request):
        """Obsługuje pobieranie postępu misji dla użytkownika przez API."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)

        guild_id_str = request.match_info.get("guild_id")
        user_id_str = request.match_info.get("user_id")

        if not all([guild_id_str, user_id_str]) or not (guild_id_str.isdigit() and user_id_str.isdigit()):
            return web.json_response({"error": "Nieprawidłowe ID serwera lub użytkownika"}, status=400)

        guild_id = int(guild_id_str)
        user_id = int(user_id_str)

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "Serwer nie znaleziony"}, status=404)
        
        member = guild.get_member(user_id)
        if not member:
            return web.json_response({"error": "Użytkownik nie znaleziony na serwerze"}, status=404)

        try:
            missions_progress_list = []
            for misja_id, misja_def in self.bot.DEFINICJE_MISJI.items():
                typ_misji = misja_def["typ_misji"]
                
                ukonczona_w_tym_cyklu = False
                poczatek_cyklu_ts = 0 # Domyślna wartość

                now_utc = datetime.now(UTC)
                if typ_misji == "dzienna":
                    reset_time_today = datetime.combine(now_utc.date(), datetime.min.time().replace(hour=config.RESET_MISJI_DZIENNYCH_GODZINA_UTC), tzinfo=UTC)
                    if now_utc >= reset_time_today:
                        poczatek_cyklu_ts = int(reset_time_today.timestamp())
                    else:
                        poczatek_cyklu_ts = int((reset_time_today - timedelta(days=1)).timestamp())
                    
                    if await self.bot.baza_danych.czy_misja_ukonczona_w_cyklu(str(user_id), str(guild_id), misja_id, poczatek_cyklu_ts):
                        ukonczona_w_tym_cyklu = True
                
                elif typ_misji == "tygodniowa":
                    today_weekday = now_utc.weekday() # Monday is 0, Sunday is 6
                    reset_weekday = config.RESET_MISJI_TYGODNIOWYCH_DZIEN_TYGODNIA # Assuming this is 0 for Monday
                    
                    # Calculate days since last reset day
                    days_since_last_reset = (today_weekday - reset_weekday + 7) % 7
                    last_reset_date = now_utc.date() - timedelta(days=days_since_last_reset)
                    reset_datetime_this_week = datetime.combine(last_reset_date, datetime.min.time().replace(hour=config.RESET_MISJI_TYGODNIOWYCH_GODZINA_UTC), tzinfo=UTC)
                    
                    if now_utc < reset_datetime_this_week:
                        # If current time is before reset time on reset day, last reset was a week ago
                        poczatek_cyklu_ts = int((reset_datetime_this_week - timedelta(weeks=1)).timestamp())
                    else:
                        # Otherwise, last reset was on the reset day of this week
                        poczatek_cyklu_ts = int(reset_datetime_this_week.timestamp())
                    
                    if await self.bot.baza_danych.czy_misja_ukonczona_w_cyklu(str(user_id), str(guild_id), misja_id, poczatek_cyklu_ts):
                        ukonczona_w_tym_cyklu = True

                elif typ_misji == "jednorazowa":
                    if await self.bot.baza_danych.czy_misja_jednorazowa_ukonczona(str(user_id), str(guild_id), misja_id):
                        ukonczona_w_tym_cyklu = True 

                mission_status = "aktywna"
                if ukonczona_w_tym_cyklu:
                    mission_status = "ukonczona_w_cyklu" if typ_misji != "jednorazowa" else "ukonczona_jednorazowa"
                
                warunki_postep = []
                for warunek_def in misja_def["warunki"]:
                    typ_warunku_misji = warunek_def["typ_warunku"]
                    wymagana_wartosc = warunek_def["wartosc"]
                    
                    # Pobierz aktualny postęp, używając poczatek_cyklu_ts dla misji cyklicznych
                    # Upewnij się, że poczatek_cyklu_ts jest przekazywany poprawnie dla wszystkich typów misji
                    aktualny_postep_tuple = await self.bot.baza_danych.pobierz_lub_stworz_postep_misji(
                        str(user_id), str(guild_id), misja_id, typ_warunku_misji, poczatek_cyklu_ts
                    )
                    aktualny_postep_val = aktualny_postep_tuple[5] # Indeks 5 to aktualna_wartosc

                    warunki_postep.append({
                        "typ_warunku": typ_warunku_misji,
                        "aktualna_wartosc": aktualny_postep_val,
                        "wymagana_wartosc": wymagana_wartosc
                    })
                
                missions_progress_list.append({
                    "mission_id": misja_id,
                    "nazwa": misja_def["nazwa"],
                    "opis": misja_def["opis"],
                    "typ_misji": typ_misji,
                    "status": mission_status,
                    "warunki_postep": warunki_postep,
                    "nagrody": misja_def.get("nagrody", {}),
                    "ikona": misja_def.get("ikona", "🎯")
                })
            
            self.bot.logger.info(f"API: Wysłano postęp misji dla {user_id} na {guild_id}.")
            return web.json_response({
                "success": True,
                "user_id": user_id,
                "guild_id": guild_id,
                "missions_progress": missions_progress_list
            })
        except Exception as e:
            self.bot.logger.error(f"API: Błąd w get_missions_progress_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def get_user_completed_missions_handler(self, request: web.Request):
        """Obsługuje pobieranie wszystkich ukończonych misji dla użytkownika."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)

        guild_id_str = request.match_info.get("guild_id")
        user_id_str = request.match_info.get("user_id")

        if not all([guild_id_str, user_id_str]) or not (guild_id_str.isdigit() and user_id_str.isdigit()):
            return web.json_response({"error": "Nieprawidłowe ID serwera lub użytkownika"}, status=400)

        guild_id = int(guild_id_str)
        user_id = int(user_id_str)

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "Serwer nie znaleziony"}, status=404)
        
        member = guild.get_member(user_id)
        if not member:
            return web.json_response({"error": "Użytkownik nie znaleziony na serwerze"}, status=404)

        try:
            completed_missions_db = await self.bot.baza_danych.pobierz_wszystkie_ukonczone_misje_uzytkownika(str(user_id), str(guild_id))
            
            completed_missions_list = []
            for mission_id, completion_timestamp in completed_missions_db:
                mission_def = config.DEFINICJE_MISJI.get(mission_id)
                if mission_def:
                    completed_missions_list.append({
                        "mission_id": mission_id,
                        "name": mission_def["nazwa"],
                        "description": mission_def["opis"],
                        "type": mission_def["typ_misji"],
                        "icon": mission_def.get("ikona", "🎯"),
                        "completed_at_utc": datetime.fromtimestamp(completion_timestamp, UTC).isoformat()
                    })
            
            self.bot.logger.info(f"API: Wysłano ukończone misje dla {user_id} na {guild_id}.")
            return web.json_response({
                "success": True,
                "user_id": user_id,
                "guild_id": guild_id,
                "completed_missions": completed_missions_list
            })
        except Exception as e:
            self.bot.logger.error(f"API: Błąd w get_user_completed_missions_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)


    async def get_server_config_handler(self, request: web.Request):
        """Obsługuje pobieranie konfiguracji bota dla danego serwera."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)

        guild_id_str = request.match_info.get("guild_id")

        if not guild_id_str or not guild_id_str.isdigit():
            return web.json_response({"error": "Nieprawidłowe ID serwera"}, status=400)

        guild_id = int(guild_id_str)

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "Serwer nie znaleziony"}, status=404)
        
        try:
            # Pobieranie konfiguracji serwera z pamięci bota (która jest ładowana z bazy)
            server_config_data = await self.bot.pobierz_konfiguracje_serwera(guild_id)
            
            # Pobieranie bonusów XP dla ról (z bazy danych)
            role_xp_bonuses_db = await self.bot.baza_danych.pobierz_bonusy_xp_rol_serwera(str(guild_id))
            role_xp_bonuses = {role_id: mnoznik for role_id, mnoznik in role_xp_bonuses_db}

            # Pobieranie konfiguracji XP dla kanałów (z bazy danych)
            channel_xp_configs_db = await self.bot.baza_danych.pobierz_wszystkie_konfiguracje_xp_kanalow_serwera(str(guild_id))
            channel_xp_configs = {
                channel_id: {"xp_zablokowane": bool(blocked), "mnoznik_xp_kanalu": multiplier}
                for channel_id, blocked, multiplier in channel_xp_configs_db
            }

            # Pobieranie nagród za poziom (z bazy danych)
            level_rewards_db = await self.bot.baza_danych.pobierz_wszystkie_nagrody_za_poziom_serwera(guild_id)
            level_rewards = {level: role_id for level, role_id in level_rewards_db}

            config_data = {
                "success": True,
                "guild_id": guild_id,
                "guild_name": guild.name,
                "bot_prefix": self.bot.prefix_bota, # Globalne ustawienie
                "welcome_channel_id": server_config_data.get("welcome_channel_id"),
                "default_role_id": server_config_data.get("default_role_id"),
                "xp_system": {
                    "xp_blocked_globally": server_config_data.get("xp_blocked_globally"),
                    "xp_multiplier_event": server_config_data.get("xp_multiplier_event"),
                    "xp_event_name": server_config_data.get("xp_event_name"),
                    "live_ranking_channel_id": server_config_data.get("live_ranking_channel_id"),
                    "live_ranking_message_id": server_config_data.get("live_ranking_message_id"),
                    "role_xp_bonuses": role_xp_bonuses,
                    "channel_xp_configs": channel_xp_configs,
                    "level_rewards": level_rewards
                },
                "giveaway_config": {
                    "default_emoji": config.GIVEAWAY_EMOJI_DEFAULT,
                    "check_interval_seconds": config.GIVEAWAY_CHECK_INTERVAL
                },
                "currency_config": {
                    "premium_currency_name": config.NAZWA_WALUTY_PREMIUM,
                    "premium_currency_symbol": config.SYMBOL_WALUTY_PREMIUM,
                    "daily_reward_amount": config.ILOSC_DUKATOW_ZA_DAILY,
                    "daily_cooldown_seconds": config.COOLDOWN_DAILY_SEKUNDY,
                    "work_reward_min": config.ILOSC_DUKATOW_ZA_PRACE_MIN,
                    "work_reward_max": config.ILOSC_DUKATOW_ZA_PRACE_MAX,
                    "work_cooldown_seconds": config.COOLDOWN_PRACA_SEKUNDY
                },
                "mission_config": {
                    "daily_reset_hour_utc": config.RESET_MISJI_DZIENNYCH_GODZINA_UTC,
                    "weekly_reset_weekday": config.RESET_MISJI_TYGODNIOWYCH_DZIEN_TYGODNIA,
                    "weekly_reset_hour_utc": config.RESET_MISJI_TYGODNIOWYCH_GODZINA_UTC
                },
                "monthly_ranking_config": {
                    "announcement_channel_id": config.ID_KANALU_OGLOSZEN_RANKINGU_MIESIECZNEGO,
                    "rewards": config.NAGRODY_RANKINGU_XP_MIESIECZNEGO
                }
            }
            self.bot.logger.info(f"API: Wysłano konfigurację dla serwera {guild_id}.")
            return web.json_response(config_data)

        except Exception as e:
            self.bot.logger.error(f"API: Błąd w get_server_config_handler dla serwera {guild_id}: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    # --- NOWE ENDPOINTY: Zapisywanie konfiguracji bota ---

    async def put_xp_config_handler(self, request: web.Request):
        """Obsługuje aktualizację globalnych ustawień XP dla serwera."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        
        guild_id_str = request.match_info.get("guild_id")
        if not guild_id_str or not guild_id_str.isdigit():
            return web.json_response({"error": "Nieprawidłowe ID serwera"}, status=400)
        guild_id = int(guild_id_str)

        try:
            data = await request.json()
            xp_blocked_globally = data.get("xp_blocked_globally")
            xp_multiplier_event = data.get("xp_multiplier_event")
            xp_event_name = data.get("xp_event_name")

            if not isinstance(xp_blocked_globally, bool):
                return web.json_response({"error": "xp_blocked_globally musi być boolean."}, status=400)
            if not isinstance(xp_multiplier_event, (int, float)) or xp_multiplier_event < 0:
                return web.json_response({"error": "xp_multiplier_event musi być nieujemną liczbą."}, status=400)
            
            # Wywołaj metodę bota do ustawienia konfiguracji XP
            await self.bot.ustaw_konfiguracje_xp_serwera(
                guild_id,
                xp_zablokowane=xp_blocked_globally,
                mnoznik_xp=xp_multiplier_event,
                nazwa_eventu=xp_event_name
            )
            self.bot.logger.info(f"API Admin: Zaktualizowano globalne ustawienia XP dla serwera {guild_id}.")
            return web.json_response({"success": True, "message": "Globalne ustawienia XP zaktualizowane pomyślnie."})
        except Exception as e:
            self.bot.logger.error(f"API Admin: Błąd w put_xp_config_handler dla serwera {guild_id}: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def put_channel_xp_config_handler(self, request: web.Request):
        """Obsługuje aktualizację ustawień XP dla konkretnego kanału."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)

        guild_id_str = request.match_info.get("guild_id")
        if not guild_id_str or not guild_id_str.isdigit():
            return web.json_response({"error": "Nieprawidłowe ID serwera"}, status=400)
        guild_id = int(guild_id_str)

        try:
            data = await request.json()
            channel_id_str = data.get("channel_id")
            xp_blocked = data.get("xp_blocked")
            xp_multiplier = data.get("xp_multiplier")

            if not channel_id_str or not channel_id_str.isdigit():
                return web.json_response({"error": "Nieprawidłowe ID kanału."}, status=400)
            if not isinstance(xp_blocked, bool):
                return web.json_response({"error": "xp_blocked musi być boolean."}, status=400)
            if not isinstance(xp_multiplier, (int, float)) or xp_multiplier < 0:
                return web.json_response({"error": "xp_multiplier musi być nieujemną liczbą."}, status=400)
            
            channel_id = int(channel_id_str)
            
            # Sprawdź, czy kanał istnieje na serwerze
            guild = self.bot.get_guild(guild_id)
            if not guild: return web.json_response({"error": "Serwer nie znaleziony."}, status=404)
            channel = guild.get_channel(channel_id)
            if not channel: return web.json_response({"error": "Kanał nie znaleziony na serwerze."}, status=404)

            # Wywołaj metodę bota do ustawienia konfiguracji kanału XP
            await self.bot.ustaw_konfiguracje_kanalu_xp_serwera(
                guild_id, channel_id, xp_blocked, xp_multiplier
            )
            self.bot.logger.info(f"API Admin: Zaktualizowano ustawienia XP dla kanału {channel_id} na serwerze {guild_id}.")
            return web.json_response({"success": True, "message": f"Ustawienia XP dla kanału {channel.name} zaktualizowane pomyślnie."})
        except Exception as e:
            self.bot.logger.error(f"API Admin: Błąd w put_channel_xp_config_handler dla serwera {guild_id}: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def delete_channel_xp_config_handler(self, request: web.Request):
        """Obsługuje usuwanie ustawień XP dla konkretnego kanału."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)

        guild_id_str = request.match_info.get("guild_id")
        channel_id_str = request.match_info.get("channel_id")

        if not all([guild_id_str, channel_id_str]) or not (guild_id_str.isdigit() and channel_id_str.isdigit()):
            return web.json_response({"error": "Nieprawidłowe ID serwera lub kanału"}, status=400)
        
        guild_id = int(guild_id_str)
        channel_id = int(channel_id_str)

        try:
            # Wywołaj metodę bota do usunięcia konfiguracji kanału XP
            await self.bot.usun_konfiguracje_kanalu_xp_serwera(str(guild_id), str(channel_id))
            self.bot.logger.info(f"API Admin: Usunięto ustawienia XP dla kanału {channel_id} na serwerze {guild_id}.")
            return web.json_response({"success": True, "message": "Konfiguracja kanału usunięta pomyślnie."})
        except Exception as e:
            self.bot.logger.error(f"API Admin: Błąd w delete_channel_xp_config_handler dla serwera {guild_id}: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def put_other_config_handler(self, request: web.Request):
        """Obsługuje aktualizację innych ustawień bota (np. kanał powitalny, domyślna rola)."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)

        guild_id_str = request.match_info.get("guild_id")
        if not guild_id_str or not guild_id_str.isdigit():
            return web.json_response({"error": "Nieprawidłowe ID serwera"}, status=400)
        guild_id = int(guild_id_str)

        try:
            data = await request.json()
            welcome_channel_id = data.get("welcome_channel_id")
            default_role_id = data.get("default_role_id")
            live_ranking_channel_id = data.get("live_ranking_channel_id")
            live_ranking_message_id = data.get("live_ranking_message_id")

            # Walidacja ID
            if welcome_channel_id is not None and not str(welcome_channel_id).isdigit():
                return web.json_response({"error": "welcome_channel_id musi być liczbą lub null."}, status=400)
            if default_role_id is not None and not str(default_role_id).isdigit():
                return web.json_response({"error": "default_role_id musi być liczbą lub null."}, status=400)
            if live_ranking_channel_id is not None and not str(live_ranking_channel_id).isdigit():
                return web.json_response({"error": "live_ranking_channel_id musi być liczbą lub null."}, status=400)
            if live_ranking_message_id is not None and not str(live_ranking_message_id).isdigit():
                return web.json_response({"error": "live_ranking_message_id musi być liczbą lub null."}, status=400)

            # Wywołaj metodę bota do ustawienia innych konfiguracji
            await self.bot.ustaw_inne_konfiguracje_serwera(
                guild_id,
                int(welcome_channel_id) if welcome_channel_id else None,
                int(default_role_id) if default_role_id else None,
                int(live_ranking_channel_id) if live_ranking_channel_id else None,
                int(live_ranking_message_id) if live_ranking_message_id else None
            )
            
            self.bot.logger.info(f"API Admin: Zaktualizowano inne ustawienia dla serwera {guild_id}.")
            return web.json_response({"success": True, "message": "Inne ustawienia zaktualizowane pomyślnie."})
        except Exception as e:
            self.bot.logger.error(f"API Admin: Błąd w put_other_config_handler dla serwera {guild_id}: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)


    # --- NOWE ENDPOINTY: Zarządzanie przedmiotami sklepu (dla panelu admina) ---

    async def post_create_shop_item_handler(self, request: web.Request):
        """Obsługuje dodawanie nowego przedmiotu do sklepu przez API (tylko dla admina)."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        
        try:
            data = await request.json()
            item_id = data.get("id")
            name = data.get("name")
            description = data.get("description")
            cost_dukaty = data.get("cost_dukaty")
            cost_krysztaly = data.get("cost_krysztaly")
            emoji = data.get("emoji")
            item_type = data.get("item_type")
            bonus_value = data.get("bonus_value")
            duration_seconds = data.get("duration_seconds")
            role_id_to_grant = data.get("role_id_to_grant")
            stock = data.get("stock", -1) # Domyślnie -1 (nieskończony)

            if not all([item_id, name, description, item_type]):
                return web.json_response({"error": "Brakujące pola: id, name, description, item_type"}, status=400)
            if cost_dukaty is not None and not isinstance(cost_dukaty, int) or (cost_dukaty is not None and cost_dukaty < 0):
                return web.json_response({"error": "Koszt w Dukatach musi być nieujemną liczbą całkowitą."}, status=400)
            if cost_krysztaly is not None and not isinstance(cost_krysztaly, int) or (cost_krysztaly is not None and cost_krysztaly < 0):
                return web.json_response({"error": "Koszt w Kryształach musi być nieujemną liczbą całkowitą."}, status=400)
            if cost_dukaty is None and cost_krysztaly is None:
                return web.json_response({"error": "Przedmiot musi mieć cenę w Dukatach lub Kryształach."}, status=400)
            if item_type == "timed_role" and not role_id_to_grant:
                return web.json_response({"error": "Dla typu 'timed_role' wymagane jest 'role_id_to_grant'."}, status=400)
            if stock is not None and not isinstance(stock, int):
                return web.json_response({"error": "Stock musi być liczbą całkowitą."}, status=400)

            # Sprawdź, czy przedmiot o danym ID już istnieje
            existing_item = await self.bot.baza_danych.pobierz_przedmiot_sklepu(item_id)
            if existing_item:
                return web.json_response({"error": f"Przedmiot o ID '{item_id}' już istnieje. Użyj PUT do aktualizacji."}, status=409) # Conflict

            await self.bot.baza_danych.dodaj_lub_zaktualizuj_przedmiot_sklepu(
                item_id, name, description, cost_dukaty, cost_krysztaly, emoji,
                item_type, bonus_value, duration_seconds, role_id_to_grant, stock
            )
            self.bot.logger.info(f"API Admin: Dodano nowy przedmiot sklepu: {item_id}")
            return web.json_response({"success": True, "message": f"Przedmiot '{name}' dodany pomyślnie."}, status=201)
        except Exception as e:
            self.bot.logger.error(f"API Admin: Błąd w post_create_shop_item_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def put_update_shop_item_handler(self, request: web.Request):
        """Obsługuje aktualizację istniejącego przedmiotu w sklepie przez API (tylko dla admina)."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        
        item_id = request.match_info.get("item_id")
        if not item_id: return web.json_response({"error": "Brak ID przedmiotu w URL"}, status=400)

        try:
            data = await request.json()
            name = data.get("name")
            description = data.get("description")
            cost_dukaty = data.get("cost_dukaty")
            cost_krysztaly = data.get("cost_krysztaly")
            emoji = data.get("emoji")
            item_type = data.get("item_type")
            bonus_value = data.get("bonus_value")
            duration_seconds = data.get("duration_seconds")
            role_id_to_grant = data.get("role_id_to_grant")
            stock = data.get("stock", -1)

            if not all([name, description, item_type]):
                return web.json_response({"error": "Brakujące pola: name, description, item_type"}, status=400)
            if cost_dukaty is not None and not isinstance(cost_dukaty, int) or (cost_dukaty is not None and cost_dukaty < 0):
                return web.json_response({"error": "Koszt w Dukatach musi być nieujemną liczbą całkowitą."}, status=400)
            if cost_krysztaly is not None and not isinstance(cost_krysztaly, int) or (cost_krysztaly is not None and cost_krysztaly < 0):
                return web.json_response({"error": "Koszt w Kryształach musi być nieujemną liczbą całkowitą."}, status=400)
            if cost_dukaty is None and cost_krysztaly is None:
                return web.json_response({"error": "Przedmiot musi mieć cenę w Dukatach lub Kryształach."}, status=400)
            if item_type == "timed_role" and not role_id_to_grant:
                return web.json_response({"error": "Dla typu 'timed_role' wymagane jest 'role_id_to_grant'."}, status=400)
            if stock is not None and not isinstance(stock, int):
                return web.json_response({"error": "Stock musi być liczbą całkowitą."}, status=400)

            # Sprawdź, czy przedmiot istnieje
            existing_item = await self.bot.baza_danych.pobierz_przedmiot_sklepu(item_id)
            if not existing_item:
                return web.json_response({"error": f"Przedmiot o ID '{item_id}' nie istnieje. Użyj POST do utworzenia."}, status=404)

            await self.bot.baza_danych.dodaj_lub_zaktualizuj_przedmiot_sklepu(
                item_id, name, description, cost_dukaty, cost_krysztaly, emoji,
                item_type, bonus_value, duration_seconds, role_id_to_grant, stock
            )
            self.bot.logger.info(f"API Admin: Zaktualizowano przedmiot sklepu: {item_id}")
            return web.json_response({"success": True, "message": f"Przedmiot '{name}' zaktualizowany pomyślnie."})
        except Exception as e:
            self.bot.logger.error(f"API Admin: Błąd w put_update_shop_item_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def delete_shop_item_handler(self, request: web.Request):
        """Obsługuje usuwanie przedmiotu ze sklepu przez API (tylko dla admina)."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        
        item_id = request.match_info.get("item_id")
        if not item_id: return web.json_response({"error": "Brak ID przedmiotu w URL"}, status=400)

        try:
            # Sprawdź, czy przedmiot istnieje
            existing_item = await self.bot.baza_danych.pobierz_przedmiot_sklepu(item_id)
            if not existing_item:
                return web.json_response({"error": f"Przedmiot o ID '{item_id}' nie istnieje."}, status=404)
            
            await self.bot.baza_danych.usun_przedmiot_sklepu(item_id)
            self.bot.logger.info(f"API Admin: Usunięto przedmiot sklepu: {item_id}")
            return web.json_response({"success": True, "message": f"Przedmiot '{item_id}' usunięty pomyślnie."})
        except Exception as e:
            self.bot.logger.error(f"API Admin: Błąd w delete_shop_item_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def get_admin_shop_items_handler(self, request: web.Request):
        """Obsługuje listowanie wszystkich przedmiotów sklepu dla panelu admina."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        try:
            shop_items_db = await self.bot.baza_danych.pobierz_wszystkie_przedmioty_sklepu()
            shop_items_processed = []
            for item_tuple in shop_items_db:
                shop_items_processed.append({
                    "id": item_tuple[0], "name": item_tuple[1], "description": item_tuple[2],
                    "cost_dukaty": item_tuple[3], "cost_krysztaly": item_tuple[4], "emoji": item_tuple[5],
                    "item_type": item_tuple[6], "bonus_value": item_tuple[7], "duration_seconds": item_tuple[8],
                    "role_id_to_grant": item_tuple[9], "stock": item_tuple[10]
                })
            return web.json_response(shop_items_processed)
        except Exception as e:
            self.bot.logger.error(f"API Admin: Błąd w get_admin_shop_items_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)

    async def get_admin_shop_item_details_handler(self, request: web.Request):
        """Obsługuje pobieranie szczegółów pojedynczego przedmiotu sklepu dla panelu admina."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        
        item_id = request.match_info.get("item_id")
        if not item_id: return web.json_response({"error": "Brak ID przedmiotu w URL"}, status=400)

        try:
            item_data_tuple = await self.bot.baza_danych.pobierz_przedmiot_sklepu(item_id)
            if not item_data_tuple:
                return web.json_response({"error": f"Przedmiot o ID '{item_id}' nie znaleziono."}, status=404)
            
            item_data = {
                "id": item_data_tuple[0], "name": item_data_tuple[1], "description": item_data_tuple[2],
                "cost_dukaty": item_data_tuple[3], "cost_krysztaly": item_tuple[4], "emoji": item_data_tuple[5],
                "item_type": item_data_tuple[6], "bonus_value": item_data_tuple[7], "duration_seconds": item_data_tuple[8],
                "role_id_to_grant": item_data_tuple[9], "stock": item_data_tuple[10]
            }
            return web.json_response(item_data)
        except Exception as e:
            self.bot.logger.error(f"API Admin: Błąd w get_admin_shop_item_details_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera."}, status=500)


    # --- NOWY ENDPOINT: Pobieranie posiadanych przedmiotów użytkownika ---
    async def get_user_inventory_handler(self, request: web.Request):
        """Obsługuje pobieranie posiadanych przedmiotów przez użytkownika."""
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        if not self.bot.main_server_id: return web.json_response({"error": "MAIN_SERVER_ID nie skonfigurowany"}, status=500)

        discord_user_id_str = request.match_info.get("discord_user_id")
        if not discord_user_id_str or not discord_user_id_str.isdigit():
            return web.json_response({"error": "Nieprawidłowe ID użytkownika"}, status=400)
        
        discord_user_id = int(discord_user_id_str)
        server_id_to_check = self.bot.main_server_id

        try:
            possessed_items_db = await self.bot.baza_danych.pobierz_posiadane_przedmioty_uzytkownika(str(discord_user_id), str(server_id_to_check))
            
            inventory_list = []
            for item_tuple in possessed_items_db:
                # p.id_posiadania, p.id_przedmiotu_sklepu, p.czas_zakupu_timestamp, p.czas_wygasniecia_timestamp,
                # p.typ_bonusu, p.wartosc_bonusu, s.name, s.emoji
                
                item_id_posiadania = item_tuple[0]
                item_id_sklepu = item_tuple[1]
                czas_zakupu_ts = item_tuple[2]
                czas_wygasniecia_ts = item_tuple[3]
                typ_bonusu = item_tuple[4]
                wartosc_bonusu = item_tuple[5]
                item_name = item_tuple[6]
                item_emoji = item_tuple[7]

                # Obliczanie pozostałego czasu
                remaining_time_seconds = None
                if czas_wygasniecia_ts is not None:
                    remaining_time_seconds = max(0, czas_wygasniecia_ts - int(time.time()))
                
                inventory_list.append({
                    "possession_id": item_id_posiadania,
                    "item_id": item_id_sklepu,
                    "name": item_name,
                    # Opis z shop_items nie jest w posiadanych_przedmiotach, można by go pobrać osobno
                    # Jeśli potrzebujesz opisu, musisz dołączyć shop_items do zapytania w bazie danych
                    "emoji": item_emoji,
                    "type": typ_bonusu,
                    "bonus_value": wartosc_bonusu,
                    "purchase_timestamp": czas_zakupu_ts,
                    "expiration_timestamp": czas_wygasniecia_ts,
                    "remaining_time_seconds": remaining_time_seconds
                })
            
            self.bot.logger.info(f"API: Wysłano ekwipunek dla użytkownika {discord_user_id} na serwerze {server_id_to_check}.")
            return web.json_response(inventory_list)
        except Exception as e:
            self.bot.logger.error(f"API: Błąd w get_user_inventory_handler dla ID {discord_user_id_str}: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera API bota przy pobieraniu ekwipunku."}, status=500)

    async def get_user_achievements_handler(self, request: web.Request):
        """
        Obsługuje pobieranie osiągnięć użytkownika, w tym postępu dla niezdobytych.
        """
        if self.bot.baza_danych is None: return web.json_response({"error": "Baza danych niedostępna"}, status=503)
        
        guild_id_str = request.match_info.get("guild_id")
        user_id_str = request.match_info.get("user_id")

        if not all([guild_id_str, user_id_str]) or not (guild_id_str.isdigit() and user_id_str.isdigit()):
            return web.json_response({"error": "Nieprawidłowe ID serwera lub użytkownika"}, status=400)

        guild_id = int(guild_id_str)
        user_id = int(user_id_str)

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "Serwer nie znaleziony"}, status=404)
        
        member = guild.get_member(user_id)
        if not member:
            return web.json_response({"error": "Użytkownik nie znaleziony na serwerze"}, status=404)

        try:
            user_xp_data = await self.bot.baza_danych.pobierz_doswiadczenie(user_id, guild_id)
            user_wallet_data = await self.bot.baza_danych.pobierz_portfel(user_id, guild_id)
            user_achievements_db = await self.bot.baza_danych.pobierz_zdobyte_osiagniecia_uzytkownika(str(user_id), str(guild_id))
            
            # Konwersja zdobytych osiągnięć na set dla szybkiego sprawdzania
            achieved_ids = {ach[0] for ach in user_achievements_db}
            achieved_data_map = {ach[0]: ach[1] for ach in user_achievements_db} # {id_osiagniecia: data_zdobycia_timestamp}

            all_achievements_status = []

            for base_id, base_def in config.DEFINICJE_OSIAGNIEC.items():
                for tier in base_def["tiery"]:
                    full_achievement_id = tier["id"]
                    is_unlocked = full_achievement_id in achieved_ids
                    
                    achievement_info = {
                        "id": full_achievement_id,
                        "name": tier["nazwa_tieru"],
                        "description": tier["opis_tieru"],
                        "icon": tier.get("odznaka_emoji", base_def.get("ikona", "⭐")),
                        "unlocked": is_unlocked,
                        "unlocked_at": achieved_data_map.get(full_achievement_id) * 1000 if is_unlocked else None, # Konwersja na milisekundy dla JS Date
                        "category": base_def.get("kategoria_osiagniecia", "Ogólne"),
                        "hidden": base_def.get("ukryte", False),
                        "progress": None, # Domyślnie None, aktualizujemy poniżej
                        "required_value": tier["wartosc_warunku"]
                    }

                    if not is_unlocked and not base_def.get("ukryte", False):
                        current_progress = 0
                        target_value = tier["wartosc_warunku"]
                        
                        if base_def["typ_warunku_bazowy"] == "liczba_wiadomosci" and user_xp_data:
                            current_progress = user_xp_data[10] # liczba_wyslanych_wiadomosci
                        elif base_def["typ_warunku_bazowy"] == "poziom_xp" and user_xp_data:
                            current_progress = user_xp_data[3] # poziom
                        elif base_def["typ_warunku_bazowy"] == "ilosc_dukatow" and user_wallet_data:
                            current_progress = user_wallet_data[2] # gwiezdne_dukaty
                        elif base_def["typ_warunku_bazowy"] == "liczba_reakcji" and user_xp_data:
                            current_progress = user_xp_data[11] # liczba_dodanych_reakcji
                        elif base_def["typ_warunku_bazowy"] == "dlugosc_streaka" and user_xp_data:
                            current_progress = user_xp_data[8] # aktualny_streak_dni
                        elif base_def["typ_warunku_bazowy"] == "liczba_wygranych_konkursow":
                            current_progress = await self.bot.baza_danych.pobierz_liczbe_wygranych_konkursow(str(user_id), str(guild_id))
                        elif base_def["typ_warunku_bazowy"] == "uzycie_komendy_kategorii" and "kategoria_komendy_warunku" in base_def:
                            current_progress = await self.bot.baza_danych.pobierz_uzycia_komend_kategorii(str(user_id), str(guild_id), base_def["kategoria_komendy_warunku"])
                        elif base_def["typ_warunku_bazowy"] == "liczba_wiadomosci_na_kanale" and "id_kanalu_warunku" in base_def:
                            current_progress = await self.bot.baza_danych.pobierz_liczbe_wiadomosci_na_kanale(str(user_id), str(guild_id), base_def["id_kanalu_warunku"]) # 0 aby tylko pobrać
                        elif base_def["typ_warunku_bazowy"] == "zakup_krysztalow":
                            # W tym przypadku, osiągnięcie jest jednorazowe i jest sprawdzane przy zakupie.
                            # Jeśli nie jest odblokowane, oznacza, że użytkownik jeszcze nie dokonał zakupu.
                            # Postęp zawsze będzie 0/1, dopóki nie zostanie odblokowane.
                            current_progress = 0 # Postęp dla tego osiągnięcia jest binarny, 0 lub 1
                            target_value = 1
                        
                        achievement_info["progress"] = min(current_progress, target_value)
                    
                    all_achievements_status.append(achievement_info)
            
            # Sortowanie osiągnięć: zdobyte najpierw, potem niezdobyte, a w każdej grupie alfabetycznie
            all_achievements_status.sort(key=lambda x: (not x["unlocked"], x["name"]))

            self.bot.logger.info(f"API: Wysłano osiągnięcia dla {user_id} na {guild_id}.")
            return web.json_response({
                "success": True,
                "user_id": user_id,
                "guild_id": guild_id,
                "achievements": all_achievements_status
            })
        except Exception as e:
            self.bot.logger.error(f"API: Błąd w get_user_achievements_handler: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera przy pobieraniu osiągnięć."}, status=500)


    async def cog_load(self):
        # Uruchomienie serwera API w tle
        # Upewnij się, że pętla asyncio jest już uruchomiona (co jest prawdą dla bota discord.py)
        asyncio.create_task(self.start_api_server())
        self.bot.logger.info("Kapsuła ApiServerCog załadowana, próba uruchomienia serwera API.")

    async def cog_unload(self):
        if self.runner:
            await self.runner.cleanup()
            self.bot.logger.info("Serwer API bota zatrzymany.")

async def setup(bot: 'BotDiscord'):
    await bot.add_cog(ApiServerCog(bot))
