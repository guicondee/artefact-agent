-- Views expostas ao agente e permissões do role somente leitura "agent_ro".
-- Pré-requisito: o role agent_ro já existe (criado por scripts/load_data.py).

-- Catálogo com as regras de preço já aplicadas, para o LLM não calcular preço.
--   * promo_*   : só preenchidos se existir promoção ATIVA (is_active) para o produto.
--   * pix_price : desconto de 5% do PIX (manual, seção 3). Não vale sobre preço promocional
--                 (manual, seção 6.2), então fica NULL quando há promoção ativa.
--   * availability : resumo de status + estoque, para decidir "disponível / sugerir alternativa".
CREATE VIEW shop.v_catalog AS
SELECT
    p.product_id,
    p.name,
    c.name AS category,
    p.description,
    p.specs,
    p.price_brl AS list_price_brl,
    pr.discount_percent AS promo_discount_percent,
    pr.description      AS promo_name,
    CASE WHEN pr.promotion_id IS NOT NULL
         THEN round(p.price_brl * (1 - pr.discount_percent / 100), 2) END AS promo_price_brl,
    CASE WHEN pr.promotion_id IS NULL
         THEN round(p.price_brl * 0.95, 2) END AS pix_price_brl,
    p.stock_quantity,
    p.status,
    CASE
        WHEN p.status = 'discontinued' THEN 'discontinued'
        WHEN p.status = 'coming_soon'  THEN 'coming_soon'
        WHEN p.stock_quantity > 0      THEN 'in_stock'
        ELSE 'out_of_stock'
    END AS availability
FROM shop.products p
JOIN shop.categories c ON c.category_id = p.category_id
LEFT JOIN shop.promotions pr ON pr.product_id = p.product_id AND pr.is_active;

COMMENT ON VIEW shop.v_catalog IS 'Catalogo de instrumentos com preco vigente, promocao ativa e disponibilidade.';

-- Princípio do menor privilégio: o agente só lê o catálogo.
-- Tabelas base (clientes, pedidos...) ficam inacessíveis; pedidos serão expostos na Etapa 3
-- por uma função que exige verificação de identidade.
REVOKE ALL ON SCHEMA shop FROM PUBLIC;
GRANT USAGE ON SCHEMA shop TO agent_ro;
GRANT SELECT ON shop.v_catalog TO agent_ro;
