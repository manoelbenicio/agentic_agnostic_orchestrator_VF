--
-- PostgreSQL database cluster dump
--

\restrict xAZQ28vuat2YQBXoE3g0QlslRXr7nVUA3TnCsPgkfcLuec1VlJbwzGPqP7HaW7R

SET default_transaction_read_only = off;

SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

--
-- Roles
--

CREATE ROLE aop_dev;
ALTER ROLE aop_dev WITH SUPERUSER INHERIT CREATEROLE CREATEDB LOGIN REPLICATION BYPASSRLS PASSWORD 'SCRAM-SHA-256$4096:Yj33QOmvVCTKU/jMGDkrvA==$xKwOF//l3zYDI16rNZJ2JwPQSR1ENwSkL36yFLeH++0=:mzkIPFPP6QZUKMew7wzh5d55xQZJwVGU1C2cZVvxiYA=';

--
-- User Configurations
--








\unrestrict xAZQ28vuat2YQBXoE3g0QlslRXr7nVUA3TnCsPgkfcLuec1VlJbwzGPqP7HaW7R

--
-- PostgreSQL database cluster dump complete
--

