from flask import Flask, request, render_template, send_file
import pandas as pd
import os
import re

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# ------------------ COLUMN CLEANING ------------------
def clean_column_name(col_name):
    col_name = str(col_name).strip().lower()
    col_name = re.sub(r"[^a-zA-Z0-9]+", "_", col_name)
    col_name = re.sub(r"_+", "_", col_name)
    col_name = col_name.strip("_")
    return col_name


# ------------------ UNIQUE ID HANDLING ------------------
def make_employee_ids_unique(df, id_column="employee_id"):
    if id_column not in df.columns:
        return df

    df[id_column] = df[id_column].astype(str).str.strip()
    df[id_column] = df[id_column].replace(["", "nan", "None", "null", "<NA>"], pd.NA)

    used_ids = set()
    updated_ids = []

    for value in df[id_column]:
        if pd.isna(value):
            updated_ids.append(pd.NA)
            continue

        if value not in used_ids:
            used_ids.add(value)
            updated_ids.append(value)
        else:
            counter = 1
            new_val = f"{value}_{counter}"
            while new_val in used_ids:
                counter += 1
                new_val = f"{value}_{counter}"

            used_ids.add(new_val)
            updated_ids.append(new_val)

    df[id_column] = updated_ids
    return df


# ------------------ DATE FORMAT ------------------
def format_mixed_date(value):
    if pd.isna(value):
        return pd.NA

    value = str(value).strip()
    if value == "":
        return pd.NA

    parsed = pd.to_datetime(value, errors="coerce")

    if pd.isna(parsed):
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)

    if pd.isna(parsed):
        return pd.NA

    return parsed.strftime("%d/%m/%Y")  # DD/MM/YYYY


# ------------------ MAIN CLEAN FUNCTION ------------------
def clean_excel_data(df):

    # Remove empty rows/columns
    df = df.dropna(axis=0, how="all")
    df = df.dropna(axis=1, how="all")

    # Clean column names
    df.columns = [clean_column_name(col) for col in df.columns]

    # Trim spaces in object columns
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip()

    # Replace null-like values and blank spaces
    df = df.replace(["", " ", "nan", "None", "null", "<NA>"], pd.NA)

    # Remove duplicates
    df = df.drop_duplicates()

    # ------------------ DATE FIX ------------------
    date_columns = []
    for col in df.columns:
        if "date" in col or "dob" in col:
            df[col] = df[col].apply(format_mixed_date)
            date_columns.append(col)

    # ------------------ NUMERICAL COLUMNS: FILL WITH AVERAGE ------------------
    for col in df.columns:
        if col in date_columns or col == "employee_id":
            continue

        numeric_series = pd.to_numeric(df[col], errors="coerce")

        # If column is fully/mostly numeric, treat as numeric
        if numeric_series.notna().sum() > 0 and numeric_series.notna().sum() >= len(df[col]) / 2:
            df[col] = numeric_series
            avg_value = df[col].mean()

            if pd.notna(avg_value):
                df[col] = df[col].fillna(avg_value)

                # Keep salary and age as integers
                if col in ["salary", "age"]:
                    df[col] = df[col].round().astype(int)
            else:
                df[col] = df[col].fillna(0)

    # ------------------ CATEGORICAL COLUMNS: FILL WITH MODE ------------------
    for col in df.columns:
        if col in date_columns or col == "employee_id":
            continue

        # Skip numeric columns already handled
        numeric_series = pd.to_numeric(df[col], errors="coerce")
        if numeric_series.notna().sum() > 0 and numeric_series.notna().sum() >= len(df[col]) / 2:
            continue

        mode_value = df[col].mode(dropna=True)
        if not mode_value.empty:
            df[col] = df[col].fillna(mode_value[0])
        else:
            df[col] = df[col].fillna("N/A")

    # ------------------ DATE COLUMNS: FILL WITH MODE ------------------
    for col in date_columns:
        mode_value = df[col].mode(dropna=True)
        if not mode_value.empty:
            df[col] = df[col].fillna(mode_value[0])
        else:
            df[col] = df[col].fillna("N/A")

    # ------------------ UNIQUE IDS ------------------
    df = make_employee_ids_unique(df, "employee_id")

    # ------------------ EMPLOYEE ID OPTIONAL FILL ------------------
    if "employee_id" in df.columns:
        mode_value = df["employee_id"].mode(dropna=True)
        if not mode_value.empty:
            df["employee_id"] = df["employee_id"].fillna(mode_value[0])

    return df


# ------------------ ROUTES ------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return "No file part found"

    file = request.files["file"]

    if file.filename == "":
        return "No file selected"

    if not file.filename.endswith((".xlsx", ".xls")):
        return "Upload only Excel files"

    input_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(input_path)

    try:
        df = pd.read_excel(input_path)
        cleaned_df = clean_excel_data(df)

        output_path = os.path.join(OUTPUT_FOLDER, "cleaned_" + file.filename)
        cleaned_df.to_excel(output_path, index=False)

        return send_file(output_path, as_attachment=True)

    except Exception as e:
        return f"Error: {str(e)}"


# ------------------ RUN APP ------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)