# Database and deployment

The app uses SQLite for local development. Vercel functions have temporary
filesystems, so production uses PostgreSQL through `DATABASE_URL` instead of a
local SQLite file.

## Vercel

1. Add a PostgreSQL provider, such as Neon, to the Vercel project.
2. Set `DATABASE_URL` to the provider's pooled PostgreSQL connection string in
   both the Vercel Production and Preview environments. Use a separate database
   for Preview so preview migrations cannot affect production data.
3. Redeploy. The Vercel build applies Django migrations before serving the
   application in each environment.

The app also accepts `POSTGRES_URL` and `POSTGRES_PRISMA_URL` when the provider
uses those environment variable names. `DATABASE_URL` is recommended.

## Render

The included `render.yaml` provisions a PostgreSQL database and connects it to
the web service. `build.sh` applies migrations during the Render build.

## Local development

When no database URL is set outside Vercel, the app uses `db.sqlite3`. Apply
migrations with:

```shell
python manage.py migrate
```

Changing the configured database does not copy existing SQLite records into
PostgreSQL. Export and import any records that must be retained before
switching databases.
