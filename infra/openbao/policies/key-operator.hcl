# No encrypt, decrypt, HMAC, export, backup, delete, policy or token administration.
path "transit/keys/pii-kek" { capabilities = ["read"] }
path "transit/keys/finance-kek" { capabilities = ["read"] }
path "transit/keys/search-hmac" { capabilities = ["read"] }
path "transit/keys/pii-kek/rotate" { capabilities = ["update"] }
path "transit/keys/finance-kek/rotate" { capabilities = ["update"] }
path "transit/keys/search-hmac/rotate" { capabilities = ["update"] }
path "transit/rewrap/pii-kek" { capabilities = ["update"] }
path "transit/rewrap/finance-kek" { capabilities = ["update"] }
path "transit/keys/pii-kek/config" {
  capabilities = ["update"]
  allowed_parameters = { "min_decryption_version" = [], "min_encryption_version" = [] }
}
path "transit/keys/finance-kek/config" {
  capabilities = ["update"]
  allowed_parameters = { "min_decryption_version" = [], "min_encryption_version" = [] }
}
path "transit/keys/search-hmac/config" {
  capabilities = ["update"]
  allowed_parameters = { "min_decryption_version" = [], "min_encryption_version" = [] }
}
path "auth/token/lookup-self" { capabilities = ["read"] }
path "auth/token/revoke-self" { capabilities = ["update"] }
path "sys/capabilities-self" { capabilities = ["update"] }
