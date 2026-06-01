# Makefile for 2HDMC

# Choose your C++ compiler here (in general g++ on Linux systems):
CC = g++
LDFLAGS=-lgsl -lgslcblas

#Optimisation level, eg: -O3
OPT=-O3
#OR debug level: -g(n=1,2,3)
DEBUG=

VPATH=src

CFLAGS= -std=c++11 -Wall $(DEBUG) $(OPT)

OBJDIR=lib
LIBDIR=$(OBJDIR)
SOURCES=THDM.cpp SM.cpp DecayTable.cpp Constraints.cpp Util.cpp
OBJECTS=$(SOURCES:.cpp=.o)
LIB=lib2HDMC.a
LDFLAGS+=-L$(LIBDIR) -l2HDMC -lgsl -lgslcblas -lm
#LDFLAGS+=-L$(LIBDIR) -l2HDMC
LIBS=
PROG=CalcPhys CalcGen CalcHiggs CalcHybrid CalcHMSSM CalcMSSM CalcInert CalcLH Demo
INCLUDE=

# To use HiggsBounds/HiggsSignals for Higgs constraints, set both of the
# following path variables to the corresponding build directories.
# Requires HiggsBounds>=5.7.0 and HiggsSignals>=2.4.0
# HiggsBounds_DIR="path-to"/HiggsBounds/higgsbounds-5.7.0/build
# HiggsSignals_DIR="path-to"/HiggsSignals/higgssignals-2.4.0/build

ifdef HiggsBounds_DIR
ifdef HiggsSignals_DIR
CFLAGS+=-DHiggsBounds
LDFLAGS+=-L$(HiggsBounds_DIR)/lib -L$(HiggsSignals_DIR)/lib -lHS -lHB -lgfortran
INCLUDE+=-I$(HiggsBounds_DIR)/../include -I$(HiggsSignals_DIR)/../include
SOURCES+=HBHS.cpp
endif
endif


#CFLAGS+=-DHiggsBounds
#LDFLAGS+=-L$(LIBDIR) -lHS -lHB -lgfortran
#SOURCES+=HBHS.cpp

.PHONY: lib clean distclean

all: lib $(PROG)

$(OBJDIR)/%.o : %.cpp %.h
	$(CC) $(CFLAGS) $(INCLUDE) -c $< -o $@

lib: $(addprefix $(LIBDIR)/, $(LIB))

$(addprefix $(LIBDIR)/, $(LIB)): $(addprefix $(OBJDIR)/, $(OBJECTS))
	@ echo "Making library $@"
	@ ar rcs $@ $(addprefix $(OBJDIR)/, $(OBJECTS))

%: %.cpp $(addprefix $(LIBDIR)/, $(LIB))
	@ echo $(CC) $< -Isrc $(CFLAGS) $(LDFLAGS) $(addprefix $(LIBDIR)/, $(LIBS)) -o $@
	@ $(CC) $< -Isrc $(CFLAGS) $(LDFLAGS) $(addprefix $(LIBDIR)/, $(LIBS)) -o $@

clean:
	@ echo "Cleaning library"
	@ rm -f $(addprefix $(OBJDIR)/, *.o)
	@ rm -f $(addprefix $(LIBDIR)/, $(LIB))

distclean:
	@ make -s clean
	@ echo "Cleaning programs"
	@ rm -f $(PROG)
