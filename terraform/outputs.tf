output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.purastone_vpc.id
}

output "alb_dns_name" {
  description = "Public DNS name of the Application Load Balancer"
  value       = aws_lb.purastone_alb.dns_name
}

output "rds_endpoint" {
  description = "Endpoint of PostgreSQL Primary RDS"
  value       = aws_db_instance.postgres_primary.endpoint
}

output "s3_storage_bucket" {
  description = "S3 bucket for invoices, LRs and backups"
  value       = aws_s3_bucket.purastone_storage.bucket
}

output "redis_endpoint" {
  description = "Primary Redis cluster configuration endpoint"
  value       = aws_elasticache_replication_group.redis_cluster.primary_endpoint_address
}
