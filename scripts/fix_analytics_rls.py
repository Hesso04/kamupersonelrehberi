import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import psycopg2

db_url = "postgresql://postgres.lxffirosgbrfptnbjvdg:BedirXaaN.04@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def main():
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        print("✅ PostgreSQL bağlantısı başarılı!")

        cur.execute("ALTER TABLE site_analytics_events ALTER COLUMN created_at SET DEFAULT timezone('utc'::text, now());")
        print("✅ created_at DEFAULT (now) başarıyla tanımlandı!")

        # RLS Aç ve Politikaları Ekle
        cur.execute("ALTER TABLE site_analytics_events ENABLE ROW LEVEL SECURITY;")
        
        cur.execute('DROP POLICY IF EXISTS "Allow anon inserts for site_analytics_events" ON site_analytics_events;')
        cur.execute("""
            CREATE POLICY "Allow anon inserts for site_analytics_events" ON site_analytics_events
            FOR INSERT TO anon, authenticated
            WITH CHECK (true);
        """)
        print("✅ Anon INSERT RLS politikası başarıyla eklendi!")

        cur.execute('DROP POLICY IF EXISTS "Allow anon select for site_analytics_events" ON site_analytics_events;')
        cur.execute("""
            CREATE POLICY "Allow anon select for site_analytics_events" ON site_analytics_events
            FOR SELECT TO anon, authenticated
            USING (true);
        """)
        print("✅ Anon SELECT RLS politikası da başarıyla eklendi!")

        cur.close()
        conn.close()
        print("🎉 Supabase Analitik RLS onarımı tamamlandı!")
    except Exception as e:
        print("❌ Hata:", e)

if __name__ == "__main__":
    main()
