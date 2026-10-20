# SirPorkALot database backup

This folder holds the **schema-only** backup of the SirPorkALot Supabase project (`hrdbdlkgeqfqyhcyrjxt`). That database stores Hogs for the Cause raffle orders for the site at [sirporkalot.vercel.app](https://sirporkalot.vercel.app).

`schema.sql` is the exact `public.orders` DDL exported on **2026-10-20**: table, indexes, check constraint, RLS, and the three policies. It contains no customer rows.

## Private data — do not commit

The actual order data (**422 rows** with buyer names, phones, and emails) is stored privately in **Stevie's OneDrive** under **SirPorkALot Backups**. `data.sql` lives there. **Never commit order dumps, CSVs of buyers, or `data.sql` to this public repo.**

At backup time:

- **Storage** was empty.
- **Auth** was empty.
- `public.orders` had **422** rows.

### Payment status on this snapshot

Stevie confirmed that **all 422 orders were paid**. In the dump, 421 rows still show `payment_status = 'pending'` because of a bug: paid status was never written back (likely the Stripe webhook / update path). Treat those `pending` values as **paid**, not unpaid. This documentation does not change the live database.

## Restore

You need `schema.sql` from this folder and `data.sql` from the private OneDrive backup. Point `DATABASE_URL` at an empty Postgres database (do not run this against production unless you intend to replace it).

```bash
psql "$DATABASE_URL" -f schema.sql
psql "$DATABASE_URL" -f data.sql
```

`data.sql` is not in git. Copy it from OneDrive first.

### Neon or plain Postgres

The policies target the Supabase roles `anon`, `authenticated`, and `service_role`. Before applying `schema.sql` on Neon or vanilla Postgres, create those roles:

```sql
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE ROLE service_role NOLOGIN;
```

Or drop the `CREATE POLICY` statements from `schema.sql` if you do not need RLS.

The table uses `gen_random_uuid()`, which needs PostgreSQL 13+ or the `pgcrypto` extension.

### Verify

```sql
select count(*) from public.orders;
```

This should return **422**.

## Related files

The app's working schema (comments, migration notes) is in [`../schema.sql`](../schema.sql). Use that when creating a new empty project. Use this folder when restoring the 2026-10-20 snapshot.
