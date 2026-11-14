| Dimensione | Sulla Luna | Cosa cercare sulla Terra |
|---|---|---|
| 1. Geologia | Crosta anortositica di altopiano; brecce e materiale espulso da impatti; bacino South Pole–Aitken | Anortosite (più è pura e ricca di calcio, meglio è); rocce da impatto |
| 2. Terreno | Bordi di cratere e creste; pareti interne > 30°; plateau piatti (Mons Mouton); massi | Rilievo ripido accanto a zone piatte; crateri da impatto |
| 3. Temperatura e luce | Sole sempre a pochi gradi sull'orizzonte (asse inclinato ~1,5°); creste illuminate fino a ~90–95% del tempo; ombre nere; zone in ombra permanente a 20–120 K (trappola fredda sotto ~110 K) | Latitudine oltre il Circolo Polare (ore all'anno con sole tra 0° e 5°, calcolabili dalla latitudine); buio totale (grotte) |
| 4. Acqua / ghiaccio | Ghiaccio nelle trappole fredde, probabilmente a chiazze, mescolato alla regolite o sepolto; regolite ghiacciata = roccia tenera ma deformabile | Permafrost con ghiaccio vicino alla superficie; ghiaccio stratificato con detriti |
| 5. Processi di superficie | Polvere sollevata dai motori in atterraggio (pannelli di IM-2 coperti); polvere abrasiva | Suoli fini e asciutti (parziale) |
| 6. Biologia | Non rilevante | — |
| 7. Sottosuolo | Ghiaccio sepolto; fosse ad alta latitudine come possibili trappole fredde | Grotte di ghiaccio con una sola apertura (trappola fredda per geometria), tubi di lava |
| 8. Operazioni | Atterraggio di precisione (IM-1 e IM-2 ribaltati); navigazione con luce radente e ombre lunghe; Terra spesso non visibile → satelliti relè; perforazione nel ghiaccio | Sito isolato senza infrastrutture; suolo ghiacciato da perforare; luce radente naturale |

Non riproducibile sulla Terra: vuoto, 20–120 K (minimo terrestre ~184 K), gravità 1/6, ombre totalmente nere (l'atmosfera diffonde luce), ghiaccio che sublima invece di fondere.

Analoghi individuati: White Mountain / Qaqortorsuaq, Groenlandia (~66,5°N, principale: anortosite più simile alla lunare + luce polare; ghiaccio nel suolo da verificare); Haughton, Isola di Devon (ghiaccio e perforazione); Lofoten e Mistastin (calibrazione); Grotta del Gelo, Etna (sottosuolo: buio, trappola fredda per geometria, tubo di lava); laboratorio per vuoto, criogenia e luce.

---

# 2. MARTE

## 2A. Missione Base umana – Arcadia Planitia
Posizione: pianure settentrionali, circa 40°N. Candidato principale di SpaceX per le prime basi (programma Mars rinviato, focus SpaceX sulla Luna dal 2026).
Obiettivo: atterraggio di grandi veicoli, base, uso del ghiaccio per acqua e propellente.

| Dimensione | Su Marte | Cosa cercare sulla Terra |
|---|---|---|
| 1. Geologia | Pianure vulcaniche e sedimentarie; regolite basaltica con perclorati (sali ossidanti) | Suoli basaltici o sedimentari aridi; presenza di sali |
| 2. Terreno | Pianura liscia, pochi massi, bassa quota (più atmosfera per frenare); crateri a piedistallo; suoli a poligoni | Pianure piatte con suoli poligonali |
| 3. Temperatura e luce | Medie latitudini: più luce e meno freddo dei poli; clima freddo e secco; forti cicli stagionali | Deserti freddi e aridi |
| 4. Acqua / ghiaccio (parametro chiave) | Ghiaccio a pochi centimetri / meno di 1 m sotto uno strato di suolo secco; il ghiaccio sublima | Permafrost con ghiaccio sotto suolo secco; meglio se il ghiaccio si consuma per sublimazione e non per fusione |
| 5. Atmosfera e polvere | CO₂ a ~6 mbar; tempeste di polvere; vento | Ambienti ventosi e polverosi (parziale) |
| 6. Biologia | Non prioritaria; ghiaccio rilevante per la protezione planetaria | — |
| 7. Sottosuolo | Ghiaccio sepolto e permafrost | Permafrost profondo; esposizioni naturali di ghiaccio sepolto |
| 8. Operazioni | Atterraggio di veicoli molto grandi; produzione di propellente da acqua + CO₂; radiazione; costruzione su suolo ghiacciato | Siti per prove di perforazione e scavo nel ghiaccio; isolamento |

Non riproducibile sulla Terra: gravità 0,38 g, atmosfera di CO₂ a 6 mbar, radiazione senza scudo magnetico, sublimazione a bassa pressione (sulla Terra il ghiaccio quasi sempre fonde).

Analoghi individuati (opinione, da verificare con fonti): Haughton (sito pratico, comune alla missione lunare); Valli Secche antartiche (riferimento per la fisica della sublimazione); Svalbard (accessibile, suoli a poligoni); Batagaika, Siberia (ghiaccio sepolto esposto; ma fonde invece di sublimare).

---

## 2B. Missione Scientifica – Jezero / Oxia Planum (meno dettagliata)
Jezero: delta di un antico lago, campioni di Perseverance. Oxia Planum: pianura argillosa, rover Rosalind Franklin (arrivo previsto fine 2030, trivella fino a 2 m).
Obiettivo: cercare tracce di vita passata (biosignature).

| Dimensione | Su Marte | Cosa cercare sulla Terra |
|---|---|---|
| 1. Geologia | Sedimenti di lago e delta, carbonati (Jezero); argille (Oxia) | Delta e sedimenti lacustri in ambienti aridi; carbonati; argille |
| 4. Acqua | Acqua antica (laghi, fiumi), non attuale | Laghi salini o alcalini, bacini prosciugati |
| 6. Biologia (parametro chiave) | Conservazione di biosignature in sedimenti fini e argille | Microbialiti e stromatoliti; ambienti estremi con microbi |
| 7. Sottosuolo | Campioni protetti dalla radiazione a ~2 m | Perforazione in sedimenti argillosi |
| 8. Operazioni | Campionamento selettivo, scelta dei campioni da riportare | Siti per addestramento alla scelta dei campioni |

Analoghi: da studiare (ipotesi: Lago Salda in Turchia, stromatoliti di Shark Bay o Pilbara in Australia).

---

# Dati utili per il software
- Magnetismo: griglia EMAG2v3 (NOAA, 2 minuti d'arco, valori in nT; versione NumPy su Zenodo).
- Luce radente: calcolabile dalla sola latitudine (ore all'anno con sole tra 0° e 5°).
- Litologia: carte geologiche con basalto, anortosite.
- Ghiaccio: mappe globali del permafrost.
- Impatti: catalogo dei crateri da impatto terrestri.
- Sottosuolo: catasti speleologici (le grotte non si vedono dai dati satellitari).
