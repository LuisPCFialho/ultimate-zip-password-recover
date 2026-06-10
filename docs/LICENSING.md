# UZPR Licensing

UZPR is free and open-source. A small optional **Pro** tier removes the
donation nag screen and unlocks future deep-mode features. Pro licenses are
issued manually after a Ko-fi (or similar) donation.

## Security model

- An Ed25519 keypair is generated **once** by the vendor (Luis).
- The **private key** lives only on the vendor's machine (`~/.uzpr-vendor/private_key.pem`).
  It **MUST never** be committed to the repository.
- The **public key** is embedded in the app as a hex constant in
  `src/uzpr/licensing/keys.py` (committed).
- A license is a signed JSON payload pasted by the user into the app, stored at
  `~/.uzpr/license.txt`.

## Token format

```
base64(payload_json) + "." + base64(signature)
```

Payload fields:

| field        | type            | notes                                    |
|--------------|-----------------|------------------------------------------|
| `email`      | string          | buyer email (for support)                |
| `tier`       | string          | currently `"pro"`                        |
| `issued_at`  | int (unix sec)  | issuance timestamp                       |
| `machine_id` | string or null  | optional — bind to a machine fingerprint |

If `machine_id` is non-null, the app will only accept the license on a machine
whose `get_machine_id()` matches.

## Vendor: generate keys (run ONCE)

```bash
python scripts/licensing/generate_vendor_keys.py
```

Copy the printed public key hex into `src/uzpr/licensing/keys.py` (replace the
`"0" * 64` placeholder), then commit that file. The private key stays in
`~/.uzpr-vendor/private_key.pem`. Back it up offline; losing it means every
issued license becomes worthless.

## Vendor: issue a license after a donation

```bash
python scripts/licensing/issue_license.py --email buyer@example.com
# or, bound to a specific machine the buyer reports:
python scripts/licensing/issue_license.py --email buyer@example.com --machine-id <hex>
```

Copy the printed token and email it to the buyer along with installation
instructions: paste into the app's License field, or drop into
`%USERPROFILE%\.uzpr\license.txt`.

## User: install a license

Either use the in-app dialog (calls `uzpr.licensing.install_license(token)`) or
manually create `%USERPROFILE%\.uzpr\license.txt` containing the token on one
line.

## Reminder

- Never commit `private_key.pem`, `vendor_private_key.pem`, or anything from
  `~/.uzpr-vendor/`. The `.gitignore` blocks them defensively.
- Rotating keys invalidates all previously-issued licenses.
