I have enough grounding. The bkcrack stage currently requires a user-supplied `plaintext_sample` and never auto-detects from STORED-entry signatures — that's the single biggest concrete lever. The budget bug is confirmed in `budget.py`. Now I'll produce the full roadmap.

# Maximizing Recovery Capability — Roadmap

## The honest ceiling (read first)

A truly random 12-character password drawn from the 95 printable ASCII characters has a keyspace of **95¹² ≈ 5.4 × 10²³ candidates**. This is not a hard target. It is, for brute force, an **impossible** one — and that is worth stating plainly before any improvement is discussed:

- On the slowest format we support (**WinZip AES-256**, hashcat `-m 13600`), a strong single GPU does ~8–19 MH/s. Exhausting 95¹² at the optimistic end (a fully-tuned RTX 4090 at ~18.9 MH/s) takes **~5.4×10²³ ÷ 1.9×10⁷ ≈ 2.9×10¹⁶ seconds ≈ 900 million GPU-years**.
- Scale it: an **8×4090 cloud rig** (~150 MH/s) still needs **~115,000 GPU-years** wall-clock. A **1,000× fleet** needs ~900,000 years. The *total compute cost* is fleet-size-invariant — at ~$0.40/GPU-hour, exhausting that keyspace costs on the order of **$3 trillion**. More GPUs only buy wall-clock, never lower the bill.
- On the *fast* format (**ZipCrypto**, `-m 17225`, ~50 GH/s/GPU), the same 95¹² is still **~340 GPU-years** on one card. Faster, still infeasible by pure search.

**No tool on earth changes this.** Passware, ElcomSoft, Hashcat, the NSA — none of them brute-force a genuinely random 12-char password. This is **cryptography working as designed**, not a limitation of our product. PBKDF2 forces ~2000 sequential SHA-1 ops per guess and has *no mathematical shortcut*; AES-256 has *no practical cryptanalytic break*. Any vendor claiming otherwise is lying or relying on the two real escape hatches below.

**The pivot — where real wins live:** we do not beat the math; we **maximize the fraction of *real* passwords we reach** and **exploit format weaknesses that sidestep the password entirely**. Two facts drive everything that follows:

1. **Most "random-looking" passwords are not random.** Humans pick `Benfica2024!`, `Summer#London21`, `Rui_1987`. These have ~30–50 bits of *effective* entropy, not 79. Smart generation (Markov, PCFG, rules, OSINT) converts an "impossible brute force" into a tractable run of 10⁹–10¹¹ likely candidates — finishing in *minutes* on one GPU. Published tests crack **50–74% of real human hashes** with dictionary + rules alone.
2. **ZipCrypto has a structural break that ignores the password.** For that one (very common, legacy) format, a known-plaintext attack recovers the keys regardless of password length — *including a 12-char random one*. This is the only honest way to "beat test-30-class" passwords, and it is the single highest-leverage feature we can ship.

---

## The single biggest lever: ZipCrypto known-plaintext

**What it is.** Legacy ZipCrypto (the `-m 17200/17225` family, `$pkzip2$` hashes) uses PKZIP's stream cipher, whose entire internal state is just three 32-bit keys (key0/key1/key2). The **Biham–Kocher known-plaintext attack** (implemented in `bkcrack`, already wired as our **Stage 13**) recovers those three keys directly from **one ciphertext/plaintext pair** — it attacks the *cipher state*, never the password. Once the keys are recovered, **every entry encrypted with that password decrypts**, and the password length/charset becomes **completely irrelevant**. A 12-char random ZipCrypto password falls in **seconds-to-minutes on a single CPU core.**

**The requirement and the gate.** bkcrack needs **≥12 known plaintext bytes (≥8 contiguous)** for one entry. The decisive applicability gate is the **compression method**, *not* the password:

- For a **STORED** (uncompressed, method 0) entry, the first bytes of ciphertext correspond *exactly* to the file's known magic header. PNG = `89 50 4E 47 0D 0A 1A 0A` (8 bytes) + IHDR `00 00 00 0D 49 48 44 52` → **16 deterministic bytes for free**. PDF = `%PDF-1.` (7–8). ZIP/DOCX/XLSX/JAR = `PK\x03\x04` + version/flags (~10). OLE/legacy-Office = `D0 CF 11 E0 A1 B1 1A E1` (8). GIF = `GIF89a` (6). Plus the **always-free CRC check-byte**: every ZipCrypto entry's 12-byte encryption header decrypts to a last byte equal to the CRC-32 high byte stored in cleartext in the central directory — one guaranteed known byte per entry that bkcrack auto-loads.
- For a **DEFLATE-compressed** entry with no external copy, the magic-header trick fails (compression scrambles the leading bytes); we then need an *exact external copy* of the contained file.

**How it applies in practice.** ZipCrypto remains extremely common in real-world archives (it's the default in many older zippers and `Right-click → Send to → Compressed folder` on older Windows). Archives bundling images/PDFs/nested-zips **stored without compression** are frequent. Where a STORED entry with a ≥12-byte deterministic header exists, this attack runs **fully automatically with zero user input** and defeats *any* password.

**Concrete implementation steps:**
1. **Parse the central directory** for every entry's `compression method` + `filename/extension` (we already inspect archives in `src/uzpr/archive/zip_inspect.py`).
2. **Maintain a signature table** mapping extension/magic → constant byte template + count of deterministic leading bytes (PNG 16, OLE 8, PDF 7–8, PK 10, GIF 6, class `CA FE BA BE`, ELF 16).
3. For each entry with `method == 0 (STORE)` and ≥12 deterministic bytes, **auto-generate `plain.bin`** and invoke bkcrack at offset 0 — **no user file needed**.
4. On success bkcrack prints `k0 k1 k2`; feed `-k k0 k1 k2 -D decrypted.zip` to decrypt all same-password entries. Optionally reconstruct the password string with `-r 9 ?b` (exhaustive to length 9; cosmetic only — the data is already recovered).
5. **Run this before any GPU work** on ZipCrypto archives.

**Honest boundary:** this does **not** apply to **WinZip AES-256** (`-m 13600`) or **RAR3/RAR5** — AES has no equivalent weakness. For those formats, password search is the only door.

---

## Tiered improvement plan

### Tier 1 — Do now (high impact, small effort)

| Item | What it unlocks | Impact | Effort | How |
|---|---|---|---|---|
| **Auto-detect exploitable plaintext for bkcrack** | Any ZipCrypto archive with a STORED entry that has a deterministic ≥12-byte header — *including 12-char random passwords* — with **zero user input**. This is the only way to beat test-30-class passwords. | Transformational | Medium-small | Parse central directory in `zip_inspect.py`; build a magic-signature table; auto-feed `plain.bin` to Stage 13. Currently Stage 13 **only runs if the user supplies `plaintext_sample`** — wire automatic detection so it fires on its own. |
| **Fix the BudgetAllocator overshoot bug** | Honest budget/cost enforcement. Confirmed: a 1000 s budget currently grants **3788 s (3.79×)** because `mark_exhausted` only returns *unused* time and never debits *consumed* time. | High | Small | In `src/uzpr/core/budget.py`, keep one decreasing `self._pool`; debit `pool -= consumed` after every stage; allocate `running = pool * prior_i / Σ remaining priors`. Add a test asserting `Σ(granted) ≤ total_budget`. |
| **Prevalence-ordered wordlist core** | The fat head of the human distribution (30–60% of typical human hashes) in the first seconds. | Transformational | Trivial | Ship `rockyou.txt` (deduped ~14M) in **native prevalence order** (never sort alphabetically); run it FIRST. (Feeds `s05_dictionary.py`.) |
| **Tiered rule escalation** | Mangled-base-word class (`P@ssw0rd!2021`, `Benfica2024`). Rules roughly double effective coverage. | Transformational | Small | `best64` → `OneRuleToRuleThemAll` (~64.5% @100M) → `pantagrule one` (~69%) → `hybrid/royce` (~73–74%) only if time allows; stop on the rules-per-percent cliff (royce needs ~8,766 rules/% vs OneRule ~895). Run OneRule + pantagrule both (they overlap by only a few thousand rules). |
| **Custom `.hcstat2` Markov ordering** | Front-loads the realistic region of any mask so the human-plausible slice is tried first — cracks more within a time cap. | High | Small | `hcstat2gen` from a target-matched corpus; `hashcat -a 3 --markov-hcstat2=custom.hcstat2 --markov-threshold=N`. Feeds `s08_mask_attack.py` / `s11_markov.py`. |
| **Optimal hashcat flags** | 10–40% on fast ZipCrypto modes; correctness on AES. | Medium | Trivial | `-w 4 -O`, pin `--backend-devices`, let autotune set loops on `-m 13600` (the 1000 PBKDF2 iters dominate; loop tuning is nearly flat there). |
| **Diagnose the real GPU throughput gap** | Recover the ~4–5× already left on the table (observed 1.84 MH/s vs ~7–9 MH/s target on a 4070 SUPER). | High | Small | Run `hashcat -b -m 13600 -w 4` and `hashcat -I`; watch `nvidia-smi` for power/thermal throttle. **The CUDA-vs-OpenCL backend is NOT the cause** — they're within 1–2% on PBKDF2 modes (OpenCL sometimes faster). Suspect laptop GPU, throttling, bad autotune, or a stale build. |

> **Note on CUDA:** bundling `nvrtc64_112_0.dll` + `nvrtc-builtins64_112.dll` next to hashcat fixes the RTC *warning* and makes CUDA mask/brute kernels JIT-compile — a correctness/availability fix, **not** a speed fix (expect 0–2% on `-m 13600`). Worth doing, but do not market it as a speedup.

### Tier 2 — Strong wins (medium effort)

| Item | What it unlocks | Impact | Effort | How |
|---|---|---|---|---|
| **Keyspace-aware EV scheduler** | More total cracks in the *same* budget by ordering stages by expected-cracks-per-second. The single biggest *orchestration* lever. | Transformational | Medium | Compute each stage's keyspace via `hashcat --keyspace`, estimate runtime from measured CPS, schedule by descending yield-density (cheap dict+rules → Markov masks/hybrids → PRINCE/combinator → capped brute force last). Box each with `--runtime`, persist `--restore`, run remaining-hashes-only. Depends on the Tier-1 budget fix. |
| **PCFG (`pcfg_cracker`)** | "Word + number + symbol" and case-mangled passwords whose base word isn't in any wordlist but whose *structure* is common — the single most common "looks random" human class. | Transformational | Medium | `trainer.py -t corpus.txt`; `pcfg_guesser.py \| hashcat -a 0`. Use `compiled-pcfg` for throughput on fast hashes. |
| **OMEN custom Markov** | Structured-but-not-in-wordlist passwords (locale letter patterns, digit/symbol placements) rockyou+rules never enumerate. | Transformational | Medium | `createNG` to train, `enumNG \| hashcat -a 0`. Validate model with `evalPW`. |
| **OSINT-seeded generation (CUPP/Mentalist)** | The single-target personal password (`Rui_Benfica1987`) that exists in **no** public corpus — highest expected-value-per-candidate for a known target. | Transformational | Small | Collect hints → keep base SMALL, push mangling into rules (Mentalist exports `.rule`) → run **first** in the queue. We already have a `Hints` structure (`core/hints.py`) and a generator (`wordlist/generator.py`) to feed this. |
| **PRINCE word-concatenation** | Multi-word / passphrase-style passwords (`summerLondon2021`) that single-word dict+rules entirely miss. | High | Small | `pp64 elems.txt \| hashcat -a 0`, curated small elements file, `--pw-min/--pw-max`, check `--keyspace` first. (Stage 10 / `wordlist/prince.py` exist.) |
| **Combinator attack (`-a 1`)** | Two/three-word passphrases hybrids can't produce (hybrid only appends a *character* mask, not a whole word). | High | Small | Add a stage: `hashcat -a 1 left.txt right.txt -j '$ ' -k 'c'`; keep both lists ≤5k (multiplicative keyspace). |
| **Portuguese (pt-PT) locale pack** | Locale passwords English lists completely miss for *this* user: Liga clubs (Benfica/Porto/Sporting), pt names (Silva/Santos), cities (Lisboa/Coimbra), pt leet/year suffixes. | High | Medium | Hand-curate a small (~few-hundred-KB) bundle of pt names + Liga clubs/chants + cities + `dadoware` vocab; expand via rules; run **early** (right after rockyou top-N) for a known-PT target. No off-the-shelf pt-PT list exists; pt-BR lists (BRDumps, wordlist-br) carry Brazilian noise — deprioritize. |
| **HIBP prevalence oracle** | Globally-optimal ordering: rank any candidate by its true real-world frequency; surfaces post-2009 common passwords rockyou lacks. | High | Medium | Bundle a top-1M plaintext extract; download-on-demand the full set; attribute per CC-BY-4.0. Raw download is *hashes* — a ranking oracle, not a directly-usable list. |

### Tier 3 — Turbo / advanced (large effort or cost)

| Item | What it unlocks | Impact | Effort | How |
|---|---|---|---|---|
| **Cloud burst (vast.ai / RunPod spot)** | Finishes *feasible* cases faster: 8×4090 (~150 MH/s) exhausts a 7-char printable AES space (~7×10¹³) in ~5–6 days; minutes for ≤6 chars. Adds only **~+0.5 random char per 8×** — sold as "faster," never "cracks anything new." | High | Medium | `--restore` checkpointing, spot/interruptible, auto-kill on first crack. $/billion AES guesses ≈ $0.0056. |
| **Hashtopolis distributed tier** | Turns any single-GPU mask/rules/PRINCE stage into an embarrassingly-parallel job; near-linear scaling. Useful only in the narrow band where the *right* attack is known but the keyspace is 1–2 orders too big for one card. | High | Large | Server computes work via `--keyspace`, hands out `-s`(skip)/`-l`(limit) chunks sized by agent benchmark. Our `engines/hashcat.py` `_build_argv()` does **not** yet emit `-s`/`-l`/`--keyspace` — adding that is the minimal enabling change. |
| **Hash-only cloud with privacy tiering** | A shippable private SaaS path: AES-256 zip hashes (`-m 13600`) leak nothing (salt+verifier+HMAC) → safe to upload. **ZipCrypto `$pkzip2$` embeds encrypted-stream bytes** → NOT content-free; must be local-only or explicit-consent. | High | Medium | Whitelist content-free modes for the "private" tier; route ZipCrypto to reduced-privacy/local; return only plaintext over TLS, retain nothing. |
| **Larger corpora download-on-demand** | The mid-tail (Weakpass, Hashmob founds, CrackStation) for slow/salted single targets. | High | Medium | Offer as "deep mode," never bundle (size + provenance). Run AFTER rockyou+rules. **Do NOT bundle COMB/Collection#1-5** — stolen credential dumps, legally unredistributable. |
| **Association / fingerprint / policygen** | Per-hash-context guesses (`-a 9`), substring recombination of known data, policy-pruned masks. | Low–Medium | Small–Medium | Niche: `-a 9` needs 1:1 hash↔hint alignment; policygen needs a known complexity policy. |
| **Neural/GAN (PassGAN/FLA)** | Little beyond what PCFG+OMEN+rules already cover. **Deprioritize.** | Low | Large | PassGAN only ~ties Best64 (34.2% on RockYou); 2025 study shows generic LLMs <1.5% Hit@10 vs PCFG ~31%. Use only as a deduped final tail stream, if ever. |

---

## What each tier lets us crack (capability table)

| Password class | Today | After Tier 1 | After Tier 2 | After Tier 3 |
|---|---|---|---|---|
| 6–7 char lowercase | Yes (mins) | Yes (mins) | Yes (mins) | Yes (mins) |
| 8-char lowercase (a-z) | Hours–Yes | Yes | Yes | Yes (faster) |
| 8-char a-z0-9 random | Days (AES) | Days | Days | Hours (cloud) |
| word + year + symbol (`Benfica2024!`) | Partial | **Yes (fast)** | **Yes (fast)** | Yes |
| 2–3 word passphrase (`summerLondon21`) | No | No | **Yes** (PRINCE/combinator) | Yes |
| OSINT-derivable personal (`Rui_1987`) | No | Partial | **Yes (fast)** | Yes |
| 9-char random printable (AES) | Infeasible | Infeasible | Infeasible | ~Weeks–months, $$ (cloud); honestly marginal |
| 10-char random printable (AES) | Infeasible | Infeasible | Infeasible | **Infeasible** (~12,000 GPU-yr) |
| **12-char random — ZipCrypto WITH exploitable known-plaintext** | No (manual) | **YES — seconds, any length** | YES | YES |
| 12-char random — ZipCrypto, no known plaintext | Infeasible | Infeasible | Infeasible | ~Years (still effectively no) |
| **12-char random — WinZip AES-256** | **Infeasible** | **Infeasible** | **Infeasible** | **Infeasible (forever)** |
| 12-char random — RAR5 | Infeasible | Infeasible | Infeasible | Infeasible (slowest KDF) |

---

## Direct answer: "will I reach test 30?"

- **Test 28–30 (random 8–12 char) on WinZip AES-256: NO. Never. By any means.** 95¹² is ~900M GPU-years / ~$3 trillion on the slowest mode; even ZipCrypto-rate math leaves it at ~340 GPU-years. No GPU, backend, flag, cloud rig, or vendor changes this. AES-256 + PBKDF2 has no shortcut. This is the cryptography succeeding.
- **Test 28–30 on ZipCrypto WITH exploitable known-plaintext: YES — instantly, via bkcrack, independent of length.** If the archive is ZipCrypto *and* contains a STORED entry with a deterministic ≥12-byte header (or you can supply one original contained file), Stage 13 recovers the keys in seconds regardless of whether the password is 12 random chars. **This is the one path that "beats" a test-30-class password — and only for ZipCrypto, never AES.**
- **Test 24–27 (word+year, short random): YES with Tier 1–2.** Word+year+symbol falls to rockyou+rules/PCFG in minutes; short random (≤7–8 printable, ≤9 alnum-lower) falls to bounded brute force, fast on ZipCrypto, days-feasible on AES with a cloud rig.

**Bottom line:** we will reach test 30 *only* on ZipCrypto-with-known-plaintext. On AES-256, test 30 is and will remain unreachable — and that is the correct, honest answer to give the user.

---

## Recommended next 5 concrete actions

1. **Auto-detect known plaintext for Stage 13.** In `src/uzpr/archive/zip_inspect.py`, extend central-directory parsing to flag `method == 0 (STORE)` entries whose extension maps to a ≥12-byte magic signature; add a signature table (PNG 16, OLE 8, PDF 7–8, PK 10, GIF 6, class/ELF). In `src/uzpr/core/stages/s13_bkcrack.py`, **remove the hard dependency on `ctx.hints.plaintext_sample`** (currently it returns `_SKIPPED_PLAN` whenever `plaintext_sample is None`, lines 45–48 / 70–77) — when a STORED signature entry exists, synthesize `plain.bin` automatically and run. This is the highest-leverage change in the entire codebase.

2. **Fix the BudgetAllocator overshoot in `src/uzpr/core/budget.py`.** Replace the growing `_paid_pool` with a single decreasing pool: debit *consumed* seconds after every stage; make `mark_exhausted` stop adding time back; allocate `pool * prior_i / Σ remaining priors`. Add a pytest asserting `Σ(granted) ≤ total_budget` for any exhaust pattern. (Confirmed 3.79× overshoot; brute-force alone got 2321 s of a 1000 s budget.)

3. **Add prevalence-ordered wordlist + tiered rules as the default cascade.** Bundle `rockyou.txt` in native order; wire `best64 → OneRuleToRuleThemAll → pantagrule one` into the dictionary/rules stages (`s05_dictionary.py`, `s07_hashcat_rules.py`), running rockyou+rules *first*, stopping on the rules-per-percent cliff. Free 30–60% coverage on typical human hashes.

4. **Implement the keyspace-aware EV scheduler in `src/uzpr/core/orchestrator.py`.** After fixing the budget, order stages by yield-density: free bkcrack/Stage-13 and dict+rules first, Markov-ordered masks and hybrids next, PRINCE/combinator after, **brute force last and hard-capped** (stop masks at ~8–9 chars fast hashes, 6–7 slow). Box each stage with `--runtime` and persist `--restore`.

5. **Diagnose the GPU throughput gap before anything else hardware-related.** Run `hashcat -b -m 13600 -w 4` and `hashcat -I` on the user's machine; compare against the ~7–9 MH/s target for a desktop 4070 SUPER. If it's near 1.84 MH/s, investigate laptop-GPU/thermal/power throttle or a stale build — **do not** chase the CUDA backend, which is within 1–2% of OpenCL on this mode and is not the cause.

**Key files:** `src/uzpr/core/budget.py` (budget bug), `src/uzpr/core/stages/s13_bkcrack.py` (known-plaintext auto-detect), `src/uzpr/archive/zip_inspect.py` (signature parsing), `src/uzpr/core/orchestrator.py` (EV scheduler), `src/uzpr/core/stages/s12_bruteforce.py` (cost-envelope/cap logic), `src/uzpr/engines/hashcat.py` (`-s`/`-l`/`--keyspace` for future distributed tier).