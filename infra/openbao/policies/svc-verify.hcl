# Leak simulation: explicitly deny all cryptographic operations, including decrypt.
path "transit/*" { capabilities = ["deny"] }
path "auth/token/lookup-self" { capabilities = ["read"] }
path "auth/token/revoke-self" { capabilities = ["update"] }
path "sys/capabilities-self" { capabilities = ["update"] }
