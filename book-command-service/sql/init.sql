-- Books database schema (RDS primary for A4)

CREATE TABLE IF NOT EXISTS books (
    ISBN        VARCHAR(20)     PRIMARY KEY,
    title       VARCHAR(255)    NOT NULL,
    Author      VARCHAR(255)    NOT NULL,
    description TEXT            NOT NULL,
    genre       VARCHAR(100)    NOT NULL,
    price       DECIMAL(10, 2)  NOT NULL,
    quantity    INT             NOT NULL,
    summary     TEXT
);
