-- Views e função da página "Análises SQL".
-- Pode ser corrido várias vezes (CREATE OR REPLACE).
-- Requer que existam as tabelas: msb_maintenance e msb_kinto_maintenance_historico.

-- 1) Contagens de ids, carids e matrículas por qualidade e status (kinto)
CREATE OR REPLACE VIEW msb_kinto_quality AS
SELECT
    "msbQuality",
    status,
    kinto,
    SUM(leasys_matriculas) AS total_matriculas,
    SUM(contagem_carids) AS total_carids,
    COUNT(*) AS total_ids
FROM msb_maintenance
WHERE TRIM(kinto) ILIKE 'kinto'
GROUP BY "msbQuality", status, kinto
ORDER BY "msbQuality";

-- 2) Relação entre os grupos de qualidade (0/1 vs 2/3/4) e o total kinto
CREATE OR REPLACE VIEW msb_kinto_qualidade_grupos AS
WITH kinto AS (
    SELECT "msbQuality"::INTEGER AS "msbQuality"
    FROM msb_maintenance
    WHERE TRIM(kinto) ILIKE 'kinto'
),
total AS (
    SELECT COUNT(*) AS total FROM kinto
)
SELECT
    CASE WHEN "msbQuality" IN (0, 1) THEN 'Qualidade 0 e 1'
         WHEN "msbQuality" IN (2, 3, 4) THEN 'Qualidade 2, 3 e 4'
         ELSE 'Outra'
    END AS grupo,
    COUNT(*) AS total_grupo,
    (SELECT total FROM total) AS total_kinto,
    ROUND(COUNT(*)::numeric / (SELECT total FROM total) * 100, 2) AS percentagem
FROM kinto
GROUP BY grupo
ORDER BY grupo;

-- 3) Kinto (último mês importado) vs maintenance atual, por qualidade 2/3/4 e status
CREATE OR REPLACE FUNCTION msb_kinto_vs_maintenance_qualidade()
RETURNS TABLE (
    "msbQuality" INTEGER,
    status TEXT,
    total_kinto_ultimo_mes BIGINT,
    total_maintenance_atual BIGINT,
    diferenca BIGINT,
    racio_evolucao_pct NUMERIC,
    pct_do_total_sistema NUMERIC
) AS $$
    WITH ultimo_periodo AS (
        SELECT ano, mes
        FROM msb_kinto_maintenance_historico
        GROUP BY ano, mes
        ORDER BY ano DESC, mes DESC
        LIMIT 1
    ),
    kinto_ultimo_ids AS (
        SELECT DISTINCT k."MsbKeyID"
        FROM msb_kinto_maintenance_historico k
        JOIN ultimo_periodo up ON k.ano = up.ano AND k.mes = up.mes
    ),
    maintenance_atual AS (
        SELECT
            m.id,
            m."msbQuality"::INTEGER AS "msbQuality",
            m.status,
            (ku."MsbKeyID" IS NOT NULL) AS ja_em_kinto
        FROM msb_maintenance m
        LEFT JOIN kinto_ultimo_ids ku ON ku."MsbKeyID" = m.id
        WHERE TRIM(m.kinto) ILIKE 'kinto' AND m."msbQuality"::INTEGER IN (2, 3, 4)
    ),
    agregado AS (
        SELECT
            "msbQuality",
            status,
            COUNT(*) FILTER (WHERE ja_em_kinto) AS total_kinto_ultimo_mes,
            COUNT(*) AS total_maintenance_atual
        FROM maintenance_atual
        GROUP BY "msbQuality", status
    ),
    total_sistema AS (
        SELECT SUM(total_maintenance_atual) AS total FROM agregado
    )
    SELECT
        "msbQuality",
        status,
        total_kinto_ultimo_mes,
        total_maintenance_atual,
        total_maintenance_atual - total_kinto_ultimo_mes AS diferenca,
        CASE WHEN total_kinto_ultimo_mes > 0
             THEN ROUND(((total_maintenance_atual::numeric / total_kinto_ultimo_mes) - 1) * 100, 2)
             ELSE NULL
        END AS racio_evolucao_pct,
        CASE WHEN (SELECT total FROM total_sistema) > 0
             THEN ROUND(total_maintenance_atual::numeric / (SELECT total FROM total_sistema) * 100, 2)
             ELSE NULL
        END AS pct_do_total_sistema
    FROM agregado
    ORDER BY 1, 2;
$$ LANGUAGE sql STABLE;
