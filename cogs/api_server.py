# cogs/api_server.py
import asyncio
from aiohttp import web
import discord 
from discord.ext import commands
import time
import typing
import uuid # Do generowania unikalnych ID transakcji dla symulacji

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
        if guild is None:
            # self.bot.logger.warning(f"API: _get_user_details otrzymało guild=None dla user_id={user_id}. Próba pobrania globalnego użytkownika.")
            try:
                user = await self.bot.fetch_user(user_id)
                if user:
                    return {"username": user.display_name, "avatar_url": str(user.display_avatar.url) if user.display_avatar else None}
            except discord.NotFound:
                # self.bot.logger.warning(f"API: Nie znaleziono globalnego użytkownika o ID {user_id} (fetch_user).")
                pass # Nie logujemy tego jako warning, bo to normalne, jeśli user nie jest na żadnym wspólnym serwerze
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
            # self.bot.logger.warning(f"API: Nie znaleziono użytkownika o ID {user_id} (fetch_user po braku na serwerze).")
            pass
        except Exception as e:
            self.bot.logger.error(f"API: Błąd podczas fetch_user (po braku na serwerze) dla ID {user_id}: {e}")
        return {"username": f"Nieznany ({user_id})", "avatar_url": None}

    async def start_api_server(self):
        app = web.Application(middlewares=[self.auth_middleware])
        app.router.add_get("/api/user_stats/{discord_user_id}", self.get_user_stats_handler)
        app.router.add_get("/api/server_stats", self.get_server_stats_handler)
        app.router.add_get("/api/ranking/xp", self.get_xp_ranking_handler)
        app.router.add_get("/api/ranking/currency", self.get_currency_ranking_handler) 
        app.router.add_get("/api/ranking/premium_currency", self.get_premium_currency_ranking_handler)
        app.router.add_get("/api/ranking/messages", self.get_messages_ranking_handler)
        app.router.add_get("/api/ranking/voicetime", self.get_voicetime_ranking_handler)
        
        app.router.add_get("/api/shop/items", self.get_shop_items_handler)
        app.router.add_post("/api/shop/buy/{item_id}", self.post_buy_item_handler)

        app.router.add_get("/api/premium/packages", self.get_premium_packages_handler)
        app.router.add_post("/api/premium/finalize_purchase/{package_id}", self.post_finalize_crystal_purchase_handler) 
        
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
            self.bot.logger.error(f"Błąd w API (get_user_stats_handler) dla ID {discord_user_id_str}: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera API bota."}, status=500)


    async def get_server_stats_handler(self, request: web.Request):
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
        try:
            limit = int(request.query.get("limit", 10))
            if not (1 <= limit <= 50): limit = 10
            ranking_data = await self._get_ranking_data("pobierz_ranking_xp", "xp_total", limit=limit)
            return web.json_response(ranking_data)
        except Exception as e:
            self.bot.logger.error(f"Błąd w API (get_xp_ranking_handler): {e}", exc_info=True)
            return web.json_response({"error": f"Wewnętrzny błąd serwera API przy pobieraniu rankingu XP: {str(e)}"}, status=500)

    async def get_currency_ranking_handler(self, request: web.Request):
        try:
            limit = int(request.query.get("limit", 10))
            if not (1 <= limit <= 50): limit = 10
            ranking_data = await self._get_ranking_data("pobierz_ranking_waluta", "currency_balance", limit=limit, typ_waluty_ranking="dukaty")
            return web.json_response(ranking_data)
        except Exception as e:
            self.bot.logger.error(f"Błąd w API (get_currency_ranking_handler - dukaty): {e}", exc_info=True)
            return web.json_response({"error": f"Wewnętrzny błąd API przy rankingu Gwiezdnych Dukatów: {str(e)}"}, status=500)

    async def get_premium_currency_ranking_handler(self, request: web.Request):
        try:
            limit = int(request.query.get("limit", 10))
            if not (1 <= limit <= 50): limit = 10
            ranking_data = await self._get_ranking_data("pobierz_ranking_waluta", "premium_currency_balance", limit=limit, typ_waluty_ranking="krysztaly")
            return web.json_response(ranking_data)
        except Exception as e:
            self.bot.logger.error(f"Błąd w API (get_premium_currency_ranking_handler - krysztaly): {e}", exc_info=True)
            return web.json_response({"error": f"Wewnętrzny błąd API przy rankingu {config.NAZWA_WALUTY_PREMIUM}: {str(e)}"}, status=500)


    async def get_messages_ranking_handler(self, request: web.Request):
        try:
            limit = int(request.query.get("limit", 10))
            if not (1 <= limit <= 50): limit = 10
            ranking_data = await self._get_ranking_data("pobierz_ranking_wiadomosci", "message_count", limit=limit)
            return web.json_response(ranking_data)
        except Exception as e:
            self.bot.logger.error(f"Błąd w API (get_messages_ranking_handler): {e}", exc_info=True)
            return web.json_response({"error": f"Wewnętrzny błąd API przy rankingu wiadomości: {str(e)}"}, status=500)

    async def get_voicetime_ranking_handler(self, request: web.Request):
        try:
            limit = int(request.query.get("limit", 10))
            if not (1 <= limit <= 50): limit = 10
            ranking_data = await self._get_ranking_data("pobierz_ranking_czas_glosowy", "voice_time_seconds", limit=limit)
            return web.json_response(ranking_data)
        except Exception as e:
            self.bot.logger.error(f"Błąd w API (get_voicetime_ranking_handler): {e}", exc_info=True)
            return web.json_response({"error": f"Wewnętrzny błąd API przy rankingu czasu głosowego: {str(e)}"}, status=500)

    async def get_shop_items_handler(self, request: web.Request):
        shop_items_processed = {}
        for item_id, item_data in config.PRZEDMIOTY_SKLEPU.items():
            shop_items_processed[item_id] = {
                "id": item_id, 
                "nazwa": item_data.get("nazwa"),
                "opis": item_data.get("opis"),
                "koszt_dukatow": item_data.get("koszt_dukatow"),
                "koszt_krysztalow": item_data.get("koszt_krysztalow"),
                "emoji": item_data.get("emoji", "🛍️"),
                "typ_bonusu": item_data.get("typ_bonusu"),
                "wartosc_bonusu": item_data.get("wartosc_mnoznika_bonusowego", item_data.get("wartosc_bonusu")), # Używamy jednej z nazw
                "czas_trwania_sekundy": item_data.get("czas_trwania_sekundy")
            }
        return web.json_response(shop_items_processed)


    async def post_buy_item_handler(self, request: web.Request):
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
        item_data = config.PRZEDMIOTY_SKLEPU.get(item_id_str)
        if not item_data: return web.json_response({"error": f"Przedmiot '{item_id_str}' nie istnieje"}, status=404)

        koszt_dukatow = item_data.get("koszt_dukatow")
        koszt_krysztalow = item_data.get("koszt_krysztalow")
        
        koszt_finalny = 0
        waluta_do_odjecia = "" 

        if currency_type_from_request == "dukaty" and koszt_dukatow is not None:
            koszt_finalny = koszt_dukatow
            waluta_do_odjecia = "dukaty"
        elif currency_type_from_request == "krysztaly" and koszt_krysztalow is not None:
            koszt_finalny = koszt_krysztalow
            waluta_do_odjecia = "krysztaly"
        elif koszt_dukatow is not None: 
            koszt_finalny = koszt_dukatow
            waluta_do_odjecia = "dukaty"
        elif koszt_krysztalow is not None: 
            koszt_finalny = koszt_krysztalow
            waluta_do_odjecia = "krysztaly"
        else:
            return web.json_response({"error": f"Przedmiot '{item_data['nazwa']}' nie ma ustalonej ceny w wybranej walucie lub w ogóle."}, status=400)

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
            
            czas_zakupu_ts = int(time.time())
            czas_wygasniecia_ts = None
            if item_data.get("czas_trwania_sekundy"):
                czas_wygasniecia_ts = czas_zakupu_ts + item_data["czas_trwania_sekundy"]
            
            wartosc_bonusu_do_zapisu = item_data.get("wartosc_mnoznika_bonusowego", item_data.get("wartosc_bonusu", 0.0))

            await self.bot.baza_danych.dodaj_przedmiot_uzytkownika(
                str(discord_user_id), str(server_id_to_check), item_id_str,
                czas_zakupu_ts, czas_wygasniecia_ts,
                item_data.get("typ_bonusu", "unknown"), wartosc_bonusu_do_zapisu
            )

            self.bot.logger.info(f"API: Użytkownik {discord_user_id} zakupił '{item_data['nazwa']}' za {koszt_finalny} ({waluta_do_odjecia}).")
            return web.json_response({
                "success": True, "message": f"Pomyślnie zakupiono: {item_data['nazwa']}!",
                "new_balance_dukaty": nowe_saldo_dukatow, "new_balance_krysztaly": nowe_saldo_krysztalow,
                "item_purchased": item_id_str
            })
        except Exception as e:
            self.bot.logger.error(f"API: Błąd zakupu '{item_id_str}' przez {discord_user_id}: {e}", exc_info=True)
            return web.json_response({"error": "Wewnętrzny błąd serwera przy zakupie."}, status=500)


    async def get_premium_packages_handler(self, request: web.Request):
        return web.json_response(config.PAKIETY_KRYSZTALOW)

    async def post_finalize_crystal_purchase_handler(self, request: web.Request):
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
            # To wymaga, aby bot miał dostęp do metody sprawdz_i_przyznaj_osiagniecia
            # i aby mógł uzyskać obiekt Member.
            guild_obj = self.bot.get_guild(server_id_to_check)
            if guild_obj:
                member = guild_obj.get_member(discord_user_id)
                if member:
                    # Sprawdzamy, czy to był pierwszy zakup na podstawie liczby transakcji dla tego usera
                    # To jest uproszczenie; lepsze byłoby sprawdzenie, czy osiągnięcie już jest.
                    # Zakładamy, że `sprawdz_i_przyznaj_osiagniecia` obsłuży logikę, czy osiągnięcie jest nowe.
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
