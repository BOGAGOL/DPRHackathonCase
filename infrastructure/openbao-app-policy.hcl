# Provision aes256-gcm96 key separately as a key custodian. App cannot export or rotate it.
path "transit/encrypt/dpr-members" { capabilities = ["update"] }
path "transit/decrypt/dpr-members" { capabilities = ["update"] }
