"""Helpers del ETL de crímenes de Chicago.

Cada módulo se importa directo, por ejemplo `from etl_helpers.data_encoding import encode_data`.
El paquete no re-exporta nada a propósito: así importar una transformación no arrastra el
cliente de MLflow, que solo necesita el subpaquete `monitoring`.
"""
