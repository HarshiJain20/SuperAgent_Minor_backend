# SuperAgent_Minor_backend

## Database migrations

Supabase schema migrations are kept in `supabase/migrations`. Run
`supabase/migrations/001_chat_history.sql` once in the Supabase SQL Editor after
enabling email/password authentication and email confirmation.

The backend needs `SUPABASE_URL` and the server-only
`SUPABASE_SERVICE_ROLE_KEY` in `.env` to persist exact chat history. The
frontend must never receive the service-role key. ChromaDB remains dedicated to
the existing RAG/PDF collection; this chat-history flow does not create or write
any ChromaDB collection.
