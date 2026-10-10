-- Private Storage bucket for uploaded electricity-bill images/PDFs (8 MB cap). No storage.objects policies are
-- defined, so only the service role (the API) can read or write; customers never get direct bucket access.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('bills', 'bills', false, 8388608, array['image/jpeg', 'image/png', 'image/webp', 'application/pdf'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;
