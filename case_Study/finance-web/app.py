from flask import Flask, render_template,request
from pymongo import MongoClient
import logging

app = Flask(__name__)

app.logger.setLevel(logging.DEBUG)

# MongoDB configuration
client = MongoClient("mongodb://localhost:27017")  
db = client["financial_analytics"]  

#private helper method to build the pipeline
"""Helper method tbuild a pipeline for dashboard screen, this support multiple
   conditonal logic to build search criteria based on the parameter passed into this method
"""
def _build_pipeline(search_customer=None,limit_operator=None,limit_amount=None):
    pipeline = [
        {
            "$lookup": {
                "from": "customers",
                "localField": "account_id",
                "foreignField": "accounts",
                "as": "customer",
            }
        },
        {
            "$unwind": "$customer"
        },
        {
            "$lookup": {
                "from": "transactions",
                "localField": "account_id",
                "foreignField": "account_id",
                "as": "transactions",
            }
        },
        {
            "$unwind": "$transactions"
        },
        {
            "$limit": 40
        },
    ]

    if search_customer:
        # search by customer
        pipeline.append({
            "$match": {
                "customer.name": {
                    "$regex": ".*" + search_customer + ".*",
                    "$options": "i"  #case insensitive
                }
            }
        })

    app.logger.debug(f"limit: {limit_amount}")
    if limit_amount:
        condition = f"${limit_operator}"
       
        pipeline.append({
                  "$match": {
                    "limit": {
                        condition: limit_amount                        
                    }
                }
        })
       
    pipeline.extend([       
        {
            "$project": {
                "_id": 0,
                "name": "$customer.name",
                "email": "$customer.email",
                "userName": "$customer.username",
                "accountLimit": "$limit",
                "transactionCount": "$transactions.transaction_count",
            }
        }
    ])

    app.logger.debug(f"pipe line: {pipeline}")
    return pipeline

"""
Helper function to build pipeline for transaction page, this pipeline will build the query
to display all the transaction rows in a tabular format. it only filter by account id    
"""
def _build_transaction_pipeline(accountid:int):
    pipeline = [        
        {
            "$match": {
                "account_id": accountid
            }
        },       
        {
            "$unwind": "$transactions"
        },
        {
            "$sort": {"transactions.date":-1}
        },        
        {
            "$project": {
                "_id": 0,
                "account_id": "$account_id",            
                "amount": "$transactions.amount",
                "date": "$transactions.date",
                "price": "$transactions.price",
                "symbol": "$transactions.symbol",
                "total": "$transactions.total",
                "transaction_code": "$transactions.transaction_code"
            }
        }
    ]
    #app.logger.debug(f"tran pipeline : {pipeline}")
    return pipeline

"""
    This pipeline will be built from the transactions page, but this is only used for grouping the data
    it uses only certain fields to be displayed, it will filter by accountId
"""
def _build_tran_groupby_pipeline(accountid:int):
        
    pipeline = [
        {
            "$match": {
                "account_id": accountid
            }
        },
        {
            "$unwind": "$transactions"
        },     
        {
            "$group": {
                "_id": {
                    "symbol": "$transactions.symbol",
                    "transaction_code": "$transactions.transaction_code"
                },
                "total_amount": {
                    "$sum": "$transactions.amount"
                },
                "total_price": {
                        "$sum": {
                            "$toDouble": "$transactions.price"
                    }
                },
                "total": {
                    "$sum": {
                            "$toDouble": "$transactions.total"
                    }     
                }
            }
        },
        {
            "$project": {
                "_id": 0, 
                "symbol": "$_id.symbol",  # extract symbol
                "transaction_code": "$_id.transaction_code",  # Project transaction_code
                "total_amount": 1,
                "total_price": 1,
                "total": 1
            }
        },
        {
            "$sort": {
                "symbol": 1  # Sort by symbol in ascending order
            }
        }   
    ]
    return pipeline
    
@app.route("/", methods=["GET", "POST"])
def home():
    limit_amount = None
    if request.method == "POST":
        # Get customer name and limit operator from the post form
        customer_name = request.form.get("customerName")
        limit_operator = request.form.get("accountLimitOperator")

        app.logger.debug(f"account limit: {request.form.get('accountLimit')}")
        #validation to handle strings in int field
        if request.form.get("accountLimit") != "" and request.form.get("accountLimit") is not None :
            limit_amount = int(request.form.get("accountLimit"))              
       
       #build pipeline
        pipeline = _build_pipeline(customer_name,limit_operator,limit_amount)        
    else:
        #without search text
        pipeline = _build_pipeline()        

    # Execute the MongoDB aggregation query
    results = list(db.accounts.aggregate(pipeline))   
    return render_template("home.html", results=results)

@app.route("/customer")
def customer():
    username = request.args.get('username')
    transactionCount = int(request.args.get('transactionCount'))

    #using find instead of aggregate.
    cust_results = db.customers.find(
        {"username": username},
        {"_id": 0, "name": 1, "email": 1, "username": 1, "birthdate": 1,"accounts":1})
        
    accounts_list = []   
    for doc in cust_results:           
        accounts_list.extend(doc['accounts'])
    
    #get accounts
    account_results = db.accounts.find(
        {"account_id": {"$in": accounts_list}},
        {"_id": 0, "limit": 1, "account_id":1, "products": 1})
    
    #having problem when iterating the above list, so need to reset the list for template page.
    cust_results.rewind()
        
    app.logger.debug(f"tran results : {accounts_list}")
    return render_template("customer.html", customer_result=cust_results,account_result=account_results,username=username,transactionCount=transactionCount)

@app.route('/transaction')
def transaction(): 

    #get all information from the strings passed into this model
    account_id = int(request.args.get("accountid"))
    username= request.args.get("username")    
    transactionCount=request.args.get("transactionCount")

    #build pipeline with search string
    pipeline = _build_transaction_pipeline(account_id)
    app.logger.debug(f"transaction pipeline : {pipeline}")
    tran_results = db.transactions.aggregate(pipeline)   

    #group by clause
    grp_pipeline = _build_tran_groupby_pipeline(account_id)
    tran_grp_results = db.transactions.aggregate(grp_pipeline)   

    #app.logger.debug(f"transaction results : {list(tran_results)}") 
    return render_template('transaction.html',tran_results=tran_results,accountid=account_id,grpby_results=tran_grp_results,username=username,transactionCount=transactionCount)

if __name__ == "__main__":
    app.run(debug=True)
