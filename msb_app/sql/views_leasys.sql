-- =============================================================================
-- Views da Leasys (equivalentes às da Kinto)
--
-- Definição usada: um MSB é "Leasys" quando tem pelo menos uma matrícula do
-- ficheiro Matriculas.csv ligada aos seus carros (leasys_matriculas > 0).
-- Ao contrário da Kinto, não depende do estado do perfil nem de datas: o estado
-- e a coluna kinto aparecem nas views só para se poder cortar por eles.
--
-- Correr (só depois de msb_maintenance existir, Fase 1):
--   psql -h localhost -U msb -d msb_prod -f sql/views_leasys.sql
--
-- Os nomes começam por "msb_", por isso a página "Análises SQL" da app
-- descobre-as sozinha.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- msb_leasys_quality
-- Por qualidade e estado do perfil: nº de matrículas Leasys, nº de carid's e nº
-- de ids (MSB). Equivalente a msb_kinto_quality.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW msb_leasys_quality AS
SELECT
    "msbQuality",
    status,
    SUM(leasys_matriculas) AS total_matriculas,
    SUM(contagem_carids)   AS total_carids,
    COUNT(*)               AS total_ids
FROM msb_maintenance
WHERE leasys_matriculas > 0
GROUP BY "msbQuality", status
ORDER BY "msbQuality", status;


-- -----------------------------------------------------------------------------
-- msb_leasys_qualidade_grupos
-- Peso dos grupos de qualidade (0 e 1 vs 2, 3 e 4) dentro da Leasys, medido
-- por ids e por matrículas. Equivalente a msb_kinto_qualidade_grupos.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW msb_leasys_qualidade_grupos AS
WITH leasys AS (
    SELECT "msbQuality"::INTEGER AS "msbQuality", leasys_matriculas
    FROM msb_maintenance
    WHERE leasys_matriculas > 0
),
total AS (
    SELECT COUNT(*) AS total_ids, SUM(leasys_matriculas) AS total_matriculas
    FROM leasys
)
SELECT
    CASE WHEN "msbQuality" IN (0, 1)    THEN 'Qualidade 0 e 1'
         WHEN "msbQuality" IN (2, 3, 4) THEN 'Qualidade 2, 3 e 4'
         ELSE 'Outra' END                                   AS grupo,
    COUNT(*)                                                AS total_ids_grupo,
    SUM(leasys_matriculas)                                  AS total_matriculas_grupo,
    (SELECT total_ids FROM total)                           AS total_ids_leasys,
    (SELECT total_matriculas FROM total)                    AS total_matriculas_leasys,
    ROUND(COUNT(*)::numeric
          / NULLIF((SELECT total_ids FROM total), 0) * 100, 2)          AS pct_ids,
    ROUND(SUM(leasys_matriculas)::numeric
          / NULLIF((SELECT total_matriculas FROM total), 0) * 100, 2)   AS pct_matriculas
FROM leasys
GROUP BY grupo
ORDER BY grupo;
