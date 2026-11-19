# Pura Stone Mineral Skincare ERP - Enterprise Cloud Infrastructure Provisioning (AWS)
terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "PuraStone-Skincare-ERP"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# 1. VPC and Subnets across 3 Availability Zones
resource "aws_vpc" "purastone_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "purastone-vpc-${var.environment}"
  }
}

resource "aws_subnet" "public" {
  count                   = 3
  vpc_id                  = aws_vpc.purastone_vpc.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 4, count.index)
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "purastone-public-subnet-${count.index + 1}"
  }
}

resource "aws_subnet" "private_app" {
  count             = 3
  vpc_id            = aws_vpc.purastone_vpc.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + 4)
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "purastone-app-subnet-${count.index + 1}"
  }
}

resource "aws_subnet" "private_db" {
  count             = 3
  vpc_id            = aws_vpc.purastone_vpc.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index + 8)
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "purastone-db-subnet-${count.index + 1}"
  }
}

# 2. KMS Customer Managed Key for Database and S3 AES-256 Encryption
resource "aws_kms_key" "purastone_kms" {
  description             = "KMS Key for Pura Stone ERP AES-256 Storage Encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  tags = {
    Name = "purastone-kms-${var.environment}"
  }
}

# 3. Encrypted S3 Bucket for Invoices, LRs, and Database Backups
resource "aws_s3_bucket" "purastone_storage" {
  bucket        = "purastone-enterprise-storage-${var.environment}"
  force_destroy = false
}

resource "aws_s3_bucket_server_side_encryption_configuration" "s3_encryption" {
  bucket = aws_s3_bucket.purastone_storage.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.purastone_kms.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "block_public" {
  bucket                  = aws_s3_bucket.purastone_storage.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 4. Multi-AZ PostgreSQL 16 RDS with Automated Snapshots
resource "aws_db_subnet_group" "db_subnets" {
  name       = "purastone-db-subnet-group-${var.environment}"
  subnet_ids = aws_subnet.private_db[*].id
}

resource "aws_security_group" "db_sg" {
  name        = "purastone-db-sg"
  description = "Allow inbound PostgreSQL traffic from App replicas"
  vpc_id      = aws_vpc.purastone_vpc.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "postgres_primary" {
  identifier              = "purastone-rds-primary-${var.environment}"
  engine                  = "postgres"
  engine_version          = "16.2"
  instance_class          = var.db_instance_class
  allocated_storage       = 100
  max_allocated_storage   = 500
  storage_type            = "gp3"
  storage_encrypted       = true
  kms_key_id              = aws_kms_key.purastone_kms.arn
  multi_az                = true
  publicly_accessible     = false
  db_subnet_group_name    = aws_db_subnet_group.db_subnets.name
  vpc_security_group_ids  = [aws_security_group.db_sg.id]
  db_name                 = "purastone_db"
  username                = var.db_username
  password                = var.db_password
  backup_retention_period = 30
  backup_window           = "02:00-03:00"
  maintenance_window      = "Sun:03:30-Sun:04:30"
  skip_final_snapshot     = false
  final_snapshot_identifier = "purastone-rds-final-${var.environment}"
  deletion_protection     = true
}

# 5. ElastiCache Redis Cluster for Celery & Distributed Locks
resource "aws_elasticache_subnet_group" "redis_subnets" {
  name       = "purastone-redis-subnets"
  subnet_ids = aws_subnet.private_app[*].id
}

resource "aws_elasticache_replication_group" "redis_cluster" {
  replication_group_id          = "purastone-redis-${var.environment}"
  replication_group_description = "Redis cluster for Celery, caching and rate limiting"
  node_type                     = "cache.t4g.medium"
  num_cache_clusters            = 2
  automatic_failover_enabled    = true
  subnet_group_name             = aws_elasticache_subnet_group.redis_subnets.name
  security_group_ids            = [aws_security_group.app_sg.id]
  at_rest_encryption_enabled    = true
  transit_encryption_enabled    = true
  kms_key_id                    = aws_kms_key.purastone_kms.arn
  engine                        = "redis"
  engine_version                = "7.0"
}

# 6. Application Load Balancer & Security Group
resource "aws_security_group" "alb_sg" {
  name        = "purastone-alb-sg"
  description = "Allow inbound HTTPS/HTTP traffic"
  vpc_id      = aws_vpc.purastone_vpc.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "app_sg" {
  name        = "purastone-app-sg"
  description = "Allow inbound traffic from ALB"
  vpc_id      = aws_vpc.purastone_vpc.id

  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "purastone_alb" {
  name               = "purastone-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = aws_subnet.public[*].id

  tags = {
    Name = "purastone-alb-${var.environment}"
  }
}
