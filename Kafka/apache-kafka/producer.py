import csv
from kafka import KafkaProducer

producer = KafkaProducer(bootstrap_servers="localhost:9092",
                         value_serializer=lambda v: v.encode("utf-8"))

with open("sms.csv", "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        label = row["label"].strip().lower()
        message = row["text"]

        if label == "spam":
            producer.send("sms_spam", message)
            print(f"[SPAM] {message}")
        else:
            producer.send("sms_ham", message)
            print(f"[HAM] {message}")

producer.flush()
producer.close()
