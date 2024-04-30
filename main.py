import configparser
import os
import re
import csv

from datetime import datetime
from pyodbc import connect

config = configparser.ConfigParser()
config.read('config.ini')


def get_list_of_files(directory_path):
    return [f"{directory_path}/{file}" for file in os.listdir(directory_path)]


def get_file_modification_date(file_path):
    return datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')


def get_database_connection():
    connection_string = config['DATABASE']['CONNECTIONSTRING']
    conn = connect(connection_string)
    return conn


def was_file_already_logged(cursor, filename, date_of_change):
    """
    Executes a SELECT statement to check if there already are records with such filename and last modification date
    :param cursor:
    :param filename:
    :param date_of_change:
    :return: True if such file was already logged
    """
    cursor.execute(
        f"""
        SELECT *
        FROM files
        WHERE sfFileName = '{filename}' AND sfFileChangeDate = '{date_of_change}'
        """
    )
    return bool(cursor.fetchone())


def save_file_information(cursor, filename, date_of_change, file_date):
    """
    Adds a new record to the files table
    :param cursor:
    :param filename:
    :param date_of_change:
    :param file_date:
    :return: ID of the inserted item
    """
    cursor.execute(
        f"""
        INSERT INTO files (sfFileName, sfFileChangeDate, sfFileDate)
        OUTPUT INSERTED.FileID
        VALUES ('{filename}', '{date_of_change}', '{file_date}')
        """
    )
    return cursor.fetchone()[0]


def process_file_data(cursor, file_path, file_id):
    """
    Forms and executes a SELECT statement for each 200 rows of the file to save its data to the file_data table.
    Commits the inserted rows only when the file was fully processed
    :param cursor:
    :param file_path:
    :param file_id:
    :return:
    """

    base_query = """
    INSERT INTO file_data (FileID, FromCustomerID, ToCustomerID, AffiliationStatus, MainAddressFlag, Position)
    VALUES 
    """
    query = base_query

    with open(file_path) as csvfile:
        reader = csv.reader(csvfile, delimiter=';')
        reader.__next__()  # To skip the header line

        for index, row in enumerate(reader):
            from_customer_id, to_customer_id, affiliation_status, main_address_flag, position = row  # Unpack row's values
            main_address_flag = int(main_address_flag == 'true')  # Convert MainAddressFlag column value to the bit type

            query += f"({file_id},'{from_customer_id}','{to_customer_id}','{affiliation_status}',{main_address_flag},'{position}'),"  # Add a new record to the INSERT statement

            if (index + 1) % 200 == 0:  # If it is a 200th row execute the INSERT statement
                query = query[:-1]
                cursor.execute(query)
                query = base_query

        if query != base_query:  # Insert the remaining rows
            query = query[:-1]
            cursor.execute(query)

    cursor.commit()


def process_file(cursor, file_path):
    """
    Main logic about file processing is here
    If the file with such filename and last modification date was already logged it will not be processed
    If the file contains no date in its name it will not be processed too
    :param cursor:
    :param file_path:
    :return:
    """
    filename = file_path.split('/')[-1]

    modification_date = get_file_modification_date(file_path)

    if was_file_already_logged(cursor, filename, modification_date):
        return

    file_date = re.search(r"[0-9]{2}.[0-9]{2}.[0-9]{4}", filename)  # Extract a date from the filename

    if not file_date:
        return

    formatted_file_date = datetime.strptime(file_date.group(), "%d.%m.%Y").strftime("%Y-%m-%d")  # Format the extracted date to the database format

    file_id = save_file_information(cursor, filename, modification_date, formatted_file_date)  # Log a new file

    process_file_data(cursor, file_path, file_id)  # Process its content


def main():
    with get_database_connection() as conn, conn.cursor() as cursor:
        directory_path = config['FILES']['DIRECTORY']

        for file_path in get_list_of_files(directory_path):
            process_file(cursor, file_path)


if __name__ == '__main__':
    main()
