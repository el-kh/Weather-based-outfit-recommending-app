-- =====================================================
-- Weather-Based Outfit Recommender – Database Schema
-- =====================================================

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- =========================
-- USERS
-- =========================
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    is_active       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT now()
);

-- =========================
-- OUTFITS
-- =========================
CREATE TABLE IF NOT EXISTS outfits (
    id                SERIAL PRIMARY KEY,
    user_id           INT REFERENCES users(id) ON DELETE CASCADE,
    name              VARCHAR(100) NOT NULL,
    category          VARCHAR(50),
    season            VARCHAR(20),
    temperature_range INT[] CHECK (array_length(temperature_range, 1) = 2),
    color             VARCHAR(30),
    image_path        TEXT,
    created_at        TIMESTAMP DEFAULT now()
);

-- =========================
-- FEEDBACK
-- =========================
CREATE TABLE IF NOT EXISTS feedback (
    id           SERIAL PRIMARY KEY,
    user_id      INT REFERENCES users(id) ON DELETE CASCADE,
    outfit_id    INT REFERENCES outfits(id) ON DELETE CASCADE,
    weather_tag  VARCHAR(20),
    liked        BOOLEAN,
    created_at   TIMESTAMP DEFAULT now()
);

-- =========================
-- WEATHER DATA
-- =========================
CREATE TABLE IF NOT EXISTS weather_data (
    id           SERIAL PRIMARY KEY,
    user_id      INT REFERENCES users(id) ON DELETE SET NULL,
    city         VARCHAR(100),
    temperature  FLOAT,
    condition    VARCHAR(50),
    humidity     INT,
    wind_speed   FLOAT,
    fetched_at   TIMESTAMP DEFAULT now()
);

-- =========================
-- RECOMMENDATIONS
-- =========================
CREATE TABLE IF NOT EXISTS recommendations (
    id           SERIAL PRIMARY KEY,
    user_id      INT REFERENCES users(id) ON DELETE CASCADE,
    outfit_id    INT REFERENCES outfits(id) ON DELETE CASCADE,
    weather_id   INT REFERENCES weather_data(id) ON DELETE SET NULL,
    score        FLOAT,
    created_at   TIMESTAMP DEFAULT now()
);

-- =========================
-- VIEW: USER FEEDBACK SUMMARY
-- =========================
CREATE OR REPLACE VIEW user_feedback_summary AS
SELECT
    u.id AS user_id,
    u.email,
    COUNT(f.*) AS total_feedbacks,
    COALESCE(SUM(CASE WHEN f.liked THEN 1 ELSE 0 END), 0) AS likes,
    COALESCE(SUM(CASE WHEN NOT f.liked THEN 1 ELSE 0 END), 0) AS dislikes
FROM users u
LEFT JOIN feedback f ON u.id = f.user_id
GROUP BY u.id, u.email;

-- =====================================================
-- End of Schema
-- =====================================================
