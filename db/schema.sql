-- Schema relacional da loja (schema "shop").
-- Recriado do zero a cada execução de emporio_agent/load_data.py (idempotente).

DROP SCHEMA IF EXISTS shop CASCADE;
CREATE SCHEMA shop;

CREATE TABLE shop.categories (
    category_id  integer PRIMARY KEY,
    name         text    NOT NULL UNIQUE,
    description  text
);

CREATE TABLE shop.products (
    product_id      integer       PRIMARY KEY,
    category_id     integer       NOT NULL REFERENCES shop.categories,
    name            text          NOT NULL UNIQUE,
    description     text,
    price_brl       numeric(10,2) NOT NULL CHECK (price_brl > 0),
    stock_quantity  integer       NOT NULL CHECK (stock_quantity >= 0),
    status          text          NOT NULL CHECK (status IN ('active', 'discontinued', 'coming_soon')),
    -- Atributos variam por categoria (violão tem "top", bateria tem "shells"), por isso jsonb.
    specs           jsonb         NOT NULL DEFAULT '{}',
    created_at      date          NOT NULL
);

-- E-mail NÃO é único: existem dois clientes com o mesmo e-mail nos dados de origem.
CREATE TABLE shop.customers (
    customer_id  integer PRIMARY KEY,
    name         text    NOT NULL,
    phone        text    NOT NULL UNIQUE,
    email        text    NOT NULL,
    city         text    NOT NULL
);

CREATE TABLE shop.orders (
    order_id            integer       PRIMARY KEY,
    customer_id         integer       NOT NULL REFERENCES shop.customers,
    order_date          date          NOT NULL,
    status              text          NOT NULL CHECK (status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')),
    total_brl           numeric(10,2) NOT NULL CHECK (total_brl > 0),
    -- Origem: "credit_6x", "pix", ... Separado em forma de pagamento e número de parcelas.
    payment_method      text          NOT NULL CHECK (payment_method IN ('pix', 'boleto', 'debit', 'credit')),
    installments        integer       NOT NULL DEFAULT 1 CHECK (installments BETWEEN 1 AND 12),
    tracking_code       text          CHECK (tracking_code ~ '^BR[A-Z0-9]{9}BR$'),
    estimated_delivery  date,
    notes               text
);

CREATE TABLE shop.order_items (
    order_id    integer NOT NULL REFERENCES shop.orders,
    product_id  integer NOT NULL REFERENCES shop.products,
    quantity    integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE shop.promotions (
    promotion_id      integer      PRIMARY KEY,
    product_id        integer      NOT NULL REFERENCES shop.products,
    discount_percent  numeric(5,2) NOT NULL CHECK (discount_percent > 0 AND discount_percent < 100),
    description       text         NOT NULL,
    is_active         boolean      NOT NULL
);

-- No máximo uma promoção ativa por produto (garante que o JOIN da view não duplica linhas).
CREATE UNIQUE INDEX one_active_promotion_per_product
    ON shop.promotions (product_id) WHERE is_active;
