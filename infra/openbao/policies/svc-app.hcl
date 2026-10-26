path "transit/encrypt/pii-kek" { capabilities = ["update"] }
path "transit/decrypt/pii-kek" { capabilities = ["update"] }
path "transit/encrypt/finance-kek" { capabilities = ["update"] }
path "transit/decrypt/finance-kek" { capabilities = ["update"] }
path "transit/hmac/search-hmac" { capabilities = ["update"] }
path "transit/hmac/search-hmac/sha2-256" { capabilities = ["update"] }
path "auth/token/lookup-self" { capabilities = ["read"] }
path "auth/token/revoke-self" { capabilities = ["update"] }
