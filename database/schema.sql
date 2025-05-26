    CREATE TABLE IF NOT EXISTS `warns` (
      `id` INTEGER PRIMARY KEY AUTOINCREMENT,
      `user_id` TEXT NOT NULL,
      `server_id` TEXT NOT NULL,
      `moderator_id` TEXT NOT NULL,
      `reason` TEXT NOT NULL,
      `created_at` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS `doswiadczenie_uzytkownika` (
      `user_id` TEXT NOT NULL,
      `server_id` TEXT NOT NULL,
      `xp` bigint DEFAULT 0,
      `poziom` int DEFAULT 0,
      `czas_na_glosowym_sekundy` bigint DEFAULT 0,
      `ostatnia_wiadomosc_timestamp` INTEGER DEFAULT 0,
      `ostatnia_reakcja_timestamp` INTEGER DEFAULT 0,
      `xp_zablokowane_indywidualnie` INTEGER DEFAULT 0,
      `aktualny_streak_dni` int DEFAULT 0,
      `ostatni_dzien_aktywnosci_streak` date DEFAULT NULL,
      `liczba_wyslanych_wiadomosci` bigint DEFAULT 0,
      `liczba_dodanych_reakcji` bigint DEFAULT 0,
      PRIMARY KEY (`user_id`, `server_id`)
    );

    CREATE TABLE IF NOT EXISTS `portfel_kronikarza` ( 
      `user_id` TEXT NOT NULL,
      `server_id` TEXT NOT NULL,
      `gwiezdne_dukaty` bigint DEFAULT 0, 
      `gwiezdne_krysztaly` bigint DEFAULT 0,
      `ostatnie_odebranie_daily_ts` INTEGER DEFAULT 0,
      PRIMARY KEY (`user_id`, `server_id`)
    );

    CREATE TABLE IF NOT EXISTS `nagrody_za_poziom` (
      `server_id` TEXT NOT NULL,
      `poziom` int NOT NULL,
      `rola_id` TEXT NOT NULL,
      PRIMARY KEY (`server_id`, `poziom`)
    );

    CREATE TABLE IF NOT EXISTS `miesieczne_xp` (
      `user_id` TEXT NOT NULL,
      `server_id` TEXT NOT NULL,
      `rok` int NOT NULL,
      `miesiac` int NOT NULL, 
      `xp_miesieczne` bigint DEFAULT 0,
      PRIMARY KEY (`user_id`, `server_id`, `rok`, `miesiac`)
    );

    CREATE TABLE IF NOT EXISTS `bonusy_xp_rol` (
      `server_id` TEXT NOT NULL,
      `rola_id` TEXT NOT NULL,
      `mnoznik_xp_roli` REAL NOT NULL DEFAULT 1.0,
      PRIMARY KEY (`server_id`, `rola_id`)
    );

    CREATE TABLE IF NOT EXISTS `konfiguracja_xp_kanalow` (
      `server_id` TEXT NOT NULL,
      `kanal_id` TEXT NOT NULL,
      `xp_zablokowane` INTEGER NOT NULL DEFAULT 0, 
      `mnoznik_xp_kanalu` REAL NOT NULL DEFAULT 1.0,
      PRIMARY KEY (`server_id`, `kanal_id`)
    );

    CREATE TABLE IF NOT EXISTS `posiadane_przedmioty` (
        `id_posiadania` INTEGER PRIMARY KEY AUTOINCREMENT,
        `user_id` TEXT NOT NULL,
        `server_id` TEXT NOT NULL,
        `id_przedmiotu_sklepu` TEXT NOT NULL, 
        `czas_zakupu_timestamp` INTEGER NOT NULL,
        `czas_wygasniecia_timestamp` INTEGER, 
        `typ_bonusu` TEXT NOT NULL, 
        `wartosc_bonusu` REAL NOT NULL, 
        FOREIGN KEY (`user_id`, `server_id`) REFERENCES `doswiadczenie_uzytkownika` (`user_id`, `server_id`) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_posiadane_przedmioty_user_server ON posiadane_przedmioty (user_id, server_id);
    CREATE INDEX IF NOT EXISTS idx_posiadane_przedmioty_wygasniecie ON posiadane_przedmioty (czas_wygasniecia_timestamp);

    CREATE TABLE IF NOT EXISTS `zdobyte_osiagniecia_uzytkownika` (
      `user_id` TEXT NOT NULL,
      `server_id` TEXT NOT NULL,
      `id_osiagniecia` TEXT NOT NULL, 
      `data_zdobycia_timestamp` INTEGER NOT NULL,
      PRIMARY KEY (`user_id`, `server_id`, `id_osiagniecia`)
    );
    CREATE INDEX IF NOT EXISTS idx_zdobyte_osiagniecia_user_server ON zdobyte_osiagniecia_uzytkownika (user_id, server_id);

    CREATE TABLE IF NOT EXISTS `aktywne_konkursy` (
        `id_konkursu` INTEGER PRIMARY KEY AUTOINCREMENT,
        `server_id` TEXT NOT NULL,
        `kanal_id` TEXT NOT NULL,
        `wiadomosc_id` TEXT NOT NULL UNIQUE, 
        `tworca_id` TEXT NOT NULL, 
        `nagroda` TEXT NOT NULL,
        `liczba_zwyciezcow` INTEGER NOT NULL DEFAULT 1,
        `czas_rozpoczecia_ts` INTEGER NOT NULL,
        `czas_zakonczenia_ts` INTEGER NOT NULL,
        `wymagana_rola_id` TEXT DEFAULT NULL, 
        `czy_zakonczony` INTEGER NOT NULL DEFAULT 0, 
        `id_zwyciezcow_json` TEXT DEFAULT NULL 
    );
    CREATE INDEX IF NOT EXISTS idx_konkursy_aktywne ON aktywne_konkursy (server_id, czy_zakonczony, czas_zakonczenia_ts);

    CREATE TABLE IF NOT EXISTS `uczestnicy_konkursow` (
        `id_wpisu` INTEGER PRIMARY KEY AUTOINCREMENT,
        `id_konkursu_wiadomosci` TEXT NOT NULL, 
        `user_id` TEXT NOT NULL,
        UNIQUE (`id_konkursu_wiadomosci`, `user_id`),
        FOREIGN KEY (`id_konkursu_wiadomosci`) REFERENCES `aktywne_konkursy` (`wiadomosc_id`) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_uczestnicy_konkurs_id ON uczestnicy_konkursow (id_konkursu_wiadomosci);

    CREATE TABLE IF NOT EXISTS `transakcje_premium` (
        `id_transakcji` INTEGER PRIMARY KEY AUTOINCREMENT,
        `user_id` TEXT NOT NULL,
        `server_id` TEXT NOT NULL,
        `id_pakietu` TEXT NOT NULL,
        `ilosc_krysztalow` INTEGER NOT NULL,
        `cena_pln` REAL,
        `id_platnosci_zewnetrznej` TEXT,
        `status_platnosci` TEXT DEFAULT 'oczekujaca',
        `timestamp_transakcji` INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_transakcje_premium_user ON transakcje_premium (user_id, server_id);
    CREATE INDEX IF NOT EXISTS idx_transakcje_premium_status ON transakcje_premium (status_platnosci);

    CREATE TABLE IF NOT EXISTS `aktywne_role_czasowe` (
        `id_wpisu_roli` INTEGER PRIMARY KEY AUTOINCREMENT,
        `user_id` TEXT NOT NULL,
        `server_id` TEXT NOT NULL,
        `rola_id` TEXT NOT NULL,
        `id_przedmiotu_sklepu` TEXT,
        `czas_nadania_timestamp` INTEGER NOT NULL,
        `czas_wygasniecia_timestamp` INTEGER NOT NULL,
        UNIQUE (`user_id`, `server_id`, `rola_id`)
    );
    CREATE INDEX IF NOT EXISTS idx_aktywne_role_czas_wygasniecia ON aktywne_role_czasowe (czas_wygasniecia_timestamp);
    CREATE INDEX IF NOT EXISTS idx_aktywne_role_user_server_rola ON aktywne_role_czasowe (user_id, server_id, rola_id);

    -- NOWE TABELE DLA SYSTEMU MISJI --
    CREATE TABLE IF NOT EXISTS `postep_misji_uzytkownika` (
        `id_postepu` INTEGER PRIMARY KEY AUTOINCREMENT,
        `user_id` TEXT NOT NULL,
        `server_id` TEXT NOT NULL,
        `id_misji` TEXT NOT NULL, 
        `typ_warunku` TEXT NOT NULL, 
        `aktualna_wartosc` INTEGER DEFAULT 0,
        `ostatni_reset_timestamp` INTEGER DEFAULT 0, 
        UNIQUE (`user_id`, `server_id`, `id_misji`, `typ_warunku`) 
    );
    CREATE INDEX IF NOT EXISTS idx_postep_misji_user_server_misja ON postep_misji_uzytkownika (user_id, server_id, id_misji);

    CREATE TABLE IF NOT EXISTS `ukonczone_misje_uzytkownika` (
        `id_ukonczenia` INTEGER PRIMARY KEY AUTOINCREMENT,
        `user_id` TEXT NOT NULL,
        `server_id` TEXT NOT NULL,
        `id_misji` TEXT NOT NULL, -- POPRAWIONA NAZWA KOLUMNY
        `data_ukonczenia_timestamp` INTEGER NOT NULL -- POPRAWIONA NAZWA KOLUMNY
        -- Usunięto redundantny PRIMARY KEY (id_ukonczenia) z końca definicji tabeli
    );
    CREATE INDEX IF NOT EXISTS idx_ukonczone_misje_user_server_misja ON ukonczone_misje_uzytkownika (user_id, server_id, id_misji);
    CREATE INDEX IF NOT EXISTS idx_ukonczone_misje_data ON ukonczone_misje_uzytkownika (data_ukonczenia_timestamp);

    