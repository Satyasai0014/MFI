import streamlit as st
import math
import pandas as pd
import datetime
import sqlite3
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode
import plotly.express as px

# Database setup
def init_db():
    conn = sqlite3.connect("emi_schedule.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_schedule (
            customer_id TEXT,
            period INTEGER,
            dpd TEXT,
            amount_outstanding REAL,
            interest REAL,
            principal_paid REAL,
            principal_outstanding REAL,
            cumulative_interest REAL,
            interest_income_outstanding REAL,
            emi_to_be_paid REAL,
            date_of_payment TEXT
            
        )
    """)
    conn.commit()
    conn.close()

# Save payment schedule to the database
def save_schedule_to_db(customer_id, payment_schedule):
    conn = sqlite3.connect("emi_schedule.db")
    cursor = conn.cursor()

    # Delete existing schedule for the customer
    cursor.execute("DELETE FROM payment_schedule WHERE customer_id = ?", (customer_id,))

    # Insert new data
    for _, row in payment_schedule.iterrows():
        cursor.execute("""
            INSERT INTO payment_schedule (
                customer_id, period, amount_outstanding, interest, principal_paid,
                principal_outstanding, cumulative_interest, interest_income_outstanding,
                emi_to_be_paid, date_of_payment, dpd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            customer_id, row['Period'], row['Amount Outstanding'], row['Interest'], row['Principal Paid'],
            row['Principal Outstanding'], row['Cumulative Interest'], row['Interest Income Outstanding'],
            row['EMI to be Paid'], row['Date of Payment'], row['DPD']
        ))
    conn.commit()
    conn.close()

# Load payment schedule from the database
def load_schedule_from_db(customer_id):
    conn = sqlite3.connect("emi_schedule.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payment_schedule WHERE customer_id = ?", (customer_id,))
    rows = cursor.fetchall()
    conn.close()

    if rows:
        columns = [
            'customer_id', 'Period', 'Amount Outstanding', 'Interest', 'Principal Paid',
            'Principal Outstanding', 'Cumulative Interest', 'Interest Income Outstanding',
            'EMI to be Paid', 'Date of Payment', 'DPD'
        ]
        return pd.DataFrame(rows, columns=columns)
    return None

# Function to calculate EMI
def calculate_emi(principal, rate, tenure, payment_frequency):
    if payment_frequency == "Daily":
        rate = rate / (365 * 100)
    elif payment_frequency == "Biweekly":
        rate = rate / (26 * 100)
    elif payment_frequency == "Weekly":
        rate = rate / (52 * 100)
    elif payment_frequency == "Monthly":
        rate = rate / (12 * 100)

    emi = (principal * rate * math.pow(1 + rate, tenure)) / (math.pow(1 + rate, tenure) - 1)
    return emi

# Function to generate payment schedule
def generate_payment_schedule(principal, rate, tenure, payment_frequency, start_date):
    emi = calculate_emi(principal, rate, tenure, payment_frequency)
    schedule = []

    principal_outstanding = principal
    cumulative_interest = 0

    for i in range(tenure):
        if payment_frequency == "Daily":
            interval_days = 1
            interest = principal_outstanding * (rate / (365 * 100))
        elif payment_frequency == "Biweekly":
            interval_days = 14
            interest = principal_outstanding * (rate / (26 * 100))
        elif payment_frequency == "Weekly":
            interval_days = 7
            interest = principal_outstanding * (rate / (52 * 100))
        elif payment_frequency == "Monthly":
            interval_days = 30
            interest = principal_outstanding * (rate / (12 * 100))

        principal_paid = emi - interest
        principal_outstanding -= principal_paid
        cumulative_interest += interest

        schedule.append({
            'Period': i + 1,
            'DPD': 'Select',  # Default value
            'Amount Outstanding': principal_outstanding + principal_paid,
            'Interest': round(interest, 3),
            'Principal Paid': round(principal_paid, 3),
            'Principal Outstanding': round(principal_outstanding, 3),
            'Cumulative Interest': round(cumulative_interest, 3),
            'Interest Income Outstanding': round(interest * (tenure - i), 3),
            'EMI to be Paid': round(emi, 3),
            'Date of Payment': (start_date + datetime.timedelta(days=interval_days * i)).strftime('%Y-%m-%d'),
            
        })
    return pd.DataFrame(schedule)
# Fetch all distinct customer IDs
def fetch_all_customers():
    conn = sqlite3.connect("emi_schedule.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT customer_id FROM payment_schedule")
    customers = [row[0] for row in cursor.fetchall()]
    conn.close()
    return customers

# Fetch DPD summary
def fetch_dpd_summary():
    conn = sqlite3.connect("emi_schedule.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT dpd, COUNT(DISTINCT customer_id) AS count
        FROM payment_schedule
        WHERE dpd IS NOT NULL
        GROUP BY dpd
    """)
    dpd_summary = cursor.fetchall()
    conn.close()
    return dpd_summary

# Fetch details for customers in a specific DPD category
def fetch_customers_by_dpd(dpd_status):
    conn = sqlite3.connect("emi_schedule.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT customer_id
        FROM payment_schedule
        WHERE dpd = ?
    """, (dpd_status,))
    customers = [row[0] for row in cursor.fetchall()]
    conn.close()
    return customers

# Prepare DPD summary based on the latest DPD status of each customer
def prepare_latest_dpd_summary():
    conn = sqlite3.connect("emi_schedule.db")
    cursor = conn.cursor()

    # Fetch the latest DPD status for each customer
    query = """
        SELECT customer_id, dpd 
        FROM (
            SELECT customer_id, dpd, MAX(period) AS latest_period
            FROM payment_schedule
            GROUP BY customer_id
        )
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    # Summarize DPD counts
    dpd_summary = {}
    for customer_id, dpd_status in rows:
        dpd_status = dpd_status if dpd_status else "No DPD"
        if dpd_status not in dpd_summary:
            dpd_summary[dpd_status] = []
        dpd_summary[dpd_status].append(customer_id)

    return dpd_summary

# Function to display all customers in a popover
def show_all_customers():
    conn = sqlite3.connect("emi_schedule.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT customer_id FROM payment_schedule")
    all_customers = [row[0] for row in cursor.fetchall()]
    conn.close()
    return all_customers
    

# Main application
def main():
    init_db()

    st.title("EMI Calculator and Payment Schedule Manager")

    tab1, tab2, tab3 = st.tabs(["Create Payment Schedule", "View/Edit Payment Schedule", "Administration Monitoring"])

    # Tab 1: Create Payment Schedule
    with tab1:
        st.header("Create Payment Schedule")

        customer_id = st.text_input("Enter Customer ID")
        principal = st.number_input("Enter Principal Amount", min_value=1000, max_value=500000, value=1000)
        interest_rate = st.number_input("Enter Interest Rate (%)", min_value=12.0, max_value=30.0, value=0.0)

        payment_frequency = st.radio("Choose Payment Frequency", ("Daily", "Biweekly", "Weekly", "Monthly"))

        if payment_frequency == "Daily":
            max_tenure = 365
        elif payment_frequency == "Biweekly":
            max_tenure = 26
        elif payment_frequency == "Weekly":
            max_tenure = 52
        elif payment_frequency == "Monthly":
            max_tenure = 36

        tenure = st.number_input("Enter Tenure", min_value=1, max_value=max_tenure, value=max_tenure // 2)
        start_date = st.date_input("Select Start Date", value=datetime.date.today())

        if st.button("Generate and Save Payment Schedule"):
            if customer_id:
                schedule = generate_payment_schedule(principal, interest_rate, tenure, payment_frequency, start_date)
                save_schedule_to_db(customer_id, schedule)
                st.success(f"Payment schedule for Customer ID {customer_id} has been saved.")
                st.subheader("Generated Payment Schedule")
                st.dataframe(schedule)

    # Tab 2: View/Edit Payment Schedule
    with tab2:
        st.header("View/Edit Payment Schedule")

        customer_id = st.text_input("Enter Customer ID to View/Edit Schedule")

        if st.button("Load Payment Schedule"):
            if customer_id:
                schedule = load_schedule_from_db(customer_id)

                if schedule is not None:
                    st.session_state.schedule = schedule
                else:
                    st.error("No schedule found for the given Customer ID.")

        if "schedule" in st.session_state and st.session_state.schedule is not None:
            schedule = st.session_state.schedule

            gb = GridOptionsBuilder.from_dataframe(schedule)
            gb.configure_default_column(editable=True)
            gb.configure_column("DPD", 
                                cellEditor="agSelectCellEditor", 
                                cellEditorParams={"values": ["Select", "0 DPD", "1< 30 DPD"]}, 
                                cellRenderer=JsCode("""
                                    function(params) {
                                        if (params.value === '0 DPD') {
                                            return '<span style="color: green;">🟢 ' + params.value + '</span>';
                                        } else if (params.value === '1< 30 DPD') {
                                            return '<span style="color: yellow;">🟡 ' + params.value + '</span>';
                                        } else {
                                            return params.value;
                                        }
                                    }
                                """))
            grid_options = gb.build()

            grid_response = AgGrid(
                schedule,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.MANUAL,  # Use manual mode to handle updates explicitly
                height=600,
                fit_columns_on_grid_load=True,
                allow_unsafe_jscode=True,
            )

            # Update the session state with the modified grid data
            st.session_state.schedule = pd.DataFrame(grid_response["data"])

            if st.button("Save Changes"):
                save_schedule_to_db(customer_id, st.session_state.schedule)  # Save to database
                st.success(f"Payment schedule for Customer ID {customer_id} saved successfully!")

            # Calculate severity if '1< 30 DPD' is selected
            exposure_data = st.session_state.schedule[st.session_state.schedule['DPD'] == '1< 30 DPD']
            if not exposure_data.empty:
                principal_exposure = exposure_data['Principal Outstanding'].sum()
                interest_exposure = exposure_data['Interest Income Outstanding'].sum()
                exposure = principal_exposure + interest_exposure
                st.markdown(
                    f"<div style='color:red; font-size:18px; font-weight:bold;'>"
                    f" 🚨 Default Detected: </div>"
                    f"<div style='font-size:16px;'>Principal Outstanding: <b>{principal_exposure:.4f}</b></div>"
                    f"<div style='font-size:16px;'>Interest Income Outstanding: <b>{interest_exposure:.4f}</b></div>"
                    f" <div style='color:red; font-size:18px;'>Total Exposure: <b> {exposure:.4f}</b></div>",
                    unsafe_allow_html=True,
                )
    # Tab 3: Administration Monitoring
    with tab3:
        st.header("Administration Monitoring")

        # Fetch data for monitoring
        all_customers = fetch_all_customers()
        dpd_summary = fetch_dpd_summary()

        st.subheader("Customer Summary")
        total_customers = len(all_customers)
        st.write(f"**Total Customers:** {total_customers}")

        # Prepare DPD summary with customer details
        dpd_data = {"DPD Status": [], "Customer Count": [], "Customer IDs": []}
        
        for dpd_status, count in dpd_summary:
            dpd_status_label = dpd_status if dpd_status else "No DPD"
            customers_in_dpd = fetch_customers_by_dpd(dpd_status_label)  # Fetch customers for this DPD status
            dpd_data["DPD Status"].append(dpd_status_label)
            dpd_data["Customer Count"].append(count)
            dpd_data["Customer IDs"].append(", ".join(customers_in_dpd) if customers_in_dpd else "None")
        
        # Convert the data into a DataFrame
        dpd_df = pd.DataFrame(dpd_data)
        
        # Filter out rows where DPD status is "Select"
        dpd_df = dpd_df[dpd_df["DPD Status"] != "Select"]
        
        # Display counts and customers by DPD status
        st.subheader("DPD Breakdown with Customer Details")
        st.dataframe(dpd_df)
        
        # Optional: Highlight rows based on DPD Status dynamically for better visibility
        st.markdown("<h4>Dynamic Highlights</h4>", unsafe_allow_html=True)
        st.table(dpd_df.style.applymap(
            lambda x: "background-color: lightpink;" if "1< 30 DPD" in x else "background-color: lightgreen;", 
            subset=["DPD Status"]
        ))

        # Show dynamic chart
        st.subheader("DPD Status Visualization")
        fig = px.pie(dpd_df, names="DPD Status", values="Customer Count", title="DPD Distribution")
        st.plotly_chart(fig)

        # Display details of customers in each DPD category as a table
        st.subheader("Customers in Each DPD Category")
        
        # Prepare data for the table
        dpd_customer_data = []
        for dpd_status in dpd_data["DPD Status"]:
            display_status = "Total" if dpd_status == 'Select' else dpd_status
            customers_in_dpd = fetch_customers_by_dpd(dpd_status)
            dpd_customer_data.append({
                "DPD Status": display_status,
                "Customer Count": len(customers_in_dpd),
                "Customer IDs": ", ".join(customers_in_dpd) if customers_in_dpd else "None"
            })

        # Create a DataFrame from the data
        dpd_customer_df = pd.DataFrame(dpd_customer_data)
        
        # Display the DataFrame as a table
        st.dataframe(dpd_customer_df)


if __name__ == "__main__":
    main()
