--
-- PostgreSQL database cluster dump
--

\restrict zrtdGeSaPxUuOe6BI5yHcvJyXipwoOIsCPEtKyldydVJanOhRX4dUURnTFFDSq7

SET default_transaction_read_only = off;

SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

--
-- Roles
--

CREATE ROLE aop_dev;
ALTER ROLE aop_dev WITH SUPERUSER INHERIT CREATEROLE CREATEDB LOGIN REPLICATION BYPASSRLS PASSWORD 'SCRAM-SHA-256$4096:C1gFqcUZtol6TV5H9Oufwg==$SwbjCZ3rGeaoQgpwFhvDi3BaJz4dtZZVnYhlB+SEA7Y=:UVkhFiWXVHTbuKoPto7Z93qPJD4EX4PrSxaHVz8Qcp0=';

--
-- User Configurations
--








\unrestrict zrtdGeSaPxUuOe6BI5yHcvJyXipwoOIsCPEtKyldydVJanOhRX4dUURnTFFDSq7

--
-- PostgreSQL database cluster dump complete
--

