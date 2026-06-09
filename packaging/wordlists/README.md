# Bundled Wordlists

## top10k.txt

The top-10 000 most common passwords, sourced from the SecLists project
(`Passwords/Common-Credentials/10-million-password-list-top-10000.txt`).
This file is freely redistributable and is bundled directly in the UZPR
installer; it powers Stage 4 of the attack cascade, which is available in
both the Free and Pro tiers.

## rockyou.txt

The RockYou wordlist, containing approximately 14 million passwords from
the 2009 RockYou data breach, sourced from the SecLists project
(`Passwords/Leaked-Databases/rockyou.txt.tar.gz`).  Due to the legally
ambiguous redistribution status of breach data, this file is **not** bundled
in the installer; instead it is downloaded on first use by the UZPR runtime
(with an explicit user acknowledgement prompt) and stored under
`%LOCALAPPDATA%\UltimateZipPasswordRecover\wordlists\rockyou.txt`.
It powers Stage 5 of the attack cascade (Free and Pro tiers).  Developers
can pre-populate it for local testing by running
`python scripts/fetch_wordlists.py fetch rockyou --i-agree`.
