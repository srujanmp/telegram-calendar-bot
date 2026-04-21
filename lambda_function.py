def lambda_handler(event, context):
	from lambda_bot import lambda_handler as real_lambda_handler

	return real_lambda_handler(event, context)
